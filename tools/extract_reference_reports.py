"""Read local DOCX XML without opening or decompressing embedded photographs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import time
import unicodedata
from zipfile import ZipFile

from lxml import etree as ET

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}
W = '{' + NS['w'] + '}'
FIELDS = ('element', 'condition_rating', 'likelihood', 'severity', 'priority')
LABELS = {
    'ELEMENT': 'element', 'CONDITIONRATING': 'condition_rating',
    'LIKLIHOOD': 'likelihood', 'LIKELIHOOD': 'likelihood',
    'SEVERITY': 'severity', 'PRIORITY': 'priority',
}


def clean(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def paragraphs(node):
    return [clean(''.join(p.xpath('.//w:t/text()', namespaces=NS)))
            for p in node.xpath('.//w:p', namespaces=NS)]


def cell_text(node):
    return '\n'.join(t for t in paragraphs(node) if t)


def label(text):
    return LABELS.get(re.sub(r'[^A-Z]', '', text.upper()))


def canonical_value(field, raw):
    value = clean(raw)
    if field == 'condition_rating':
        value = re.sub(r'^(\d+)\s*[.)]\s*', r'\1. ', value)
    return value


def split_description(text):
    result = {'observation': [], 'recommendation': []}
    current = None
    for part in re.split(r'\b(OBSERVATIONS?|RECOMMENDATIONS?)\b\s*:?', text, flags=re.I):
        heading = part.strip().upper()
        if re.fullmatch(r'OBSERVATIONS?', heading):
            current = 'observation'
        elif re.fullmatch(r'RECOMMENDATIONS?', heading):
            current = 'recommendation'
        elif current and part.strip():
            result[current].append(part.strip())
    return {key: '\n'.join(values).strip() for key, values in result.items()}


def read_report(path, root, texts_dir):
    relative = path.relative_to(root).as_posix()
    is_review = bool(re.search(r'_(?:jz|sa|srw)(?:[ _]|\.|$)', path.name, re.I))
    role = 'primary' if len(Path(relative).parts) == 2 and path.name.startswith('12477-SIR-') and not is_review else 'supporting'
    with ZipFile(path) as archive:
        info = {entry.filename.replace('\\', '/'): entry for entry in archive.infolist()}
        xml = archive.read(info['word/document.xml'])
        document = ET.fromstring(xml, ET.XMLParser(resolve_entities=False, no_network=True))
        tables = []
        for table_number, table in enumerate(document.xpath('./w:body/w:tbl', namespaces=NS), 1):
            values, fills = {}, {}
            rows = table.findall('w:tr', NS)
            for row in rows:
                cells = row.findall('w:tc', NS)
                for index, cell in enumerate(cells[:-1]):
                    field = label(cell_text(cell))
                    if not field:
                        continue
                    following = cells[index + 1:]
                    value_cell = next((c for c in following if cell_text(c)), following[0])
                    values[field] = cell_text(value_cell)
                    fills[field] = value_cell.xpath('./w:tcPr/w:shd/@w:fill', namespaces=NS)
            if 'element' not in values or len(values) < 3:
                continue
            records = []
            for row_number, row in enumerate(rows, 1):
                cells = row.findall('w:tc', NS)
                if any(label(cell_text(c)) for c in cells):
                    continue
                photo_count = len(row.xpath('.//a:blip', namespaces=NS))
                descriptive = next((c for c in reversed(cells)
                                    if re.search(r'\b(?:OBSERVATION|RECOMMENDATION)', cell_text(c), re.I)), None)
                if descriptive is not None:
                    text = cell_text(descriptive)
                    records.append({'row': row_number, 'photo_count': photo_count,
                                    'raw_text': text, **split_description(text)})
                elif photo_count:
                    last_cell = cells[-1]
                    merge = last_cell.find('w:tcPr/w:vMerge', NS)
                    if records and merge is not None and merge.get(W + 'val', 'continue') == 'continue':
                        records[-1]['photo_count'] += photo_count
                    else:
                        records.append({'row': row_number, 'photo_count': photo_count,
                                        'raw_text': '', 'observation': '', 'recommendation': ''})
            tables.append({
                'table': table_number, 'fields': values, 'fills': fills,
                'missing_fields': [f for f in FIELDS if f not in values],
                'grid_twips': table.xpath('./w:tblGrid/w:gridCol/@w:w', namespaces=NS),
                'table_style': table.xpath('./w:tblPr/w:tblStyle/@w:val', namespaces=NS),
                'records': records,
            })
        text_path = texts_dir / Path(relative).with_suffix('.txt')
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text('\n'.join(paragraphs(document)), encoding='utf-8')
        sections = []
        for section in document.xpath('.//w:sectPr', namespaces=NS):
            sections.append({
                'page_size': [dict(p.attrib) for p in section.findall('w:pgSz', NS)],
                'margins': [dict(p.attrib) for p in section.findall('w:pgMar', NS)],
            })
        return {
            'source': relative, 'role': role, 'file_bytes': path.stat().st_size,
            'xml_bytes_read': len(xml), 'media_count': sum(n.startswith('word/media/') for n in info),
            'text_file': text_path.as_posix(), 'sections': sections,
            'inspection_tables': tables,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    root = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    texts_dir = output / 'report_texts'
    reports, errors = [], []
    for path in sorted(root.rglob('*.docx')):
        if path.name.startswith('~$'):
            continue
        try:
            reports.append(read_report(path, root, texts_dir))
        except Exception as error:
            errors.append({'source': path.relative_to(root).as_posix(), 'error': str(error)})

    # Primary report options form the default menu; supporting versions are retained for review.
    grouped = {field: {} for field in FIELDS}
    for report in reports:
        for table in report['inspection_tables']:
            for field, raw in table['fields'].items():
                value = canonical_value(field, raw)
                key = value.casefold()
                entry = grouped[field].setdefault(key, {
                    'value': value, 'raw_variants': set(), 'sources': set(),
                    'primary_sources': set(), 'primary_occurrences': 0,
                    'supporting_occurrences': 0, 'fills': Counter(),
                })
                entry['raw_variants'].add(raw)
                entry['sources'].add(report['source'])
                entry[report['role'] + '_occurrences'] += 1
                if report['role'] == 'primary':
                    entry['primary_sources'].add(report['source'])
                    entry['fills'].update(table['fills'].get(field, []))

    menus, full_options = {}, {}
    for field, entries in grouped.items():
        def sort_key(entry):
            match = re.match(r'^(\d+)\.', entry['value']) if field == 'condition_rating' else None
            return (int(match.group(1)) if match else 999, entry['value'].casefold())
        full_options[field] = []
        for entry in sorted(entries.values(), key=sort_key):
            full_options[field].append({**entry, 'raw_variants': sorted(entry['raw_variants']),
                                       'sources': sorted(entry['sources']),
                                       'primary_sources': sorted(entry['primary_sources']),
                                       'fills': dict(entry['fills'])})
        menus[field] = [e['value'] for e in full_options[field] if e['primary_occurrences']]

    layout_counts = Counter()
    primary_tables = 0
    description_counts = Counter()
    description_library = {'observation': {}, 'recommendation': {}}
    for report in reports:
        if report['role'] != 'primary':
            continue
        for table in report['inspection_tables']:
            primary_tables += 1
            layout_counts['/'.join(table['grid_twips'])] += 1
            for record in table['records']:
                for field in ('observation', 'recommendation'):
                    if record[field]:
                        description_counts[field] += 1
                        text = record[field]
                        key = clean(text).casefold()
                        entry = description_library[field].setdefault(key, {
                            'text': text, 'elements': set(), 'sources': set(), 'occurrences': 0,
                        })
                        entry['elements'].add(table['fields']['element'])
                        entry['sources'].add(report['source'])
                        entry['occurrences'] += 1

    for field, entries in description_library.items():
        description_library[field] = [
            {**e, 'elements': sorted(e['elements']), 'sources': sorted(e['sources'])}
            for e in sorted(entries.values(), key=lambda e: (-e['occurrences'], e['text']))
        ]

    review_items = []
    proposed = dict(menus)
    rating_groups = defaultdict(list)
    for entry in full_options['condition_rating']:
        if not entry['primary_occurrences']:
            continue
        match = re.match(r'^(\d+)\.', entry['value'])
        rating_groups[match.group(1) if match else entry['value']].append(entry)
    proposed['condition_rating'] = []
    for group, entries in rating_groups.items():
        preferred = max(entries, key=lambda e: e['primary_occurrences'])
        proposed['condition_rating'].append(preferred['value'])
        if len(entries) > 1:
            review_items.append({'field': 'condition_rating', 'rating': group,
                                 'proposed_value': preferred['value'],
                                 'rule': 'Most frequent wording for the same numeric rating; requires confirmation.',
                                 'variants': [{'value': e['value'], 'occurrences': e['primary_occurrences'],
                                               'sources': e['primary_sources']} for e in entries]})
    proposed['severity'] = []
    for value in menus['severity']:
        parts = re.split(r'\.\s+(?=[A-Z])', value, maxsplit=1)
        candidate = parts[0]
        if candidate not in proposed['severity']:
            proposed['severity'].append(candidate)
        if len(parts) > 1:
            review_items.append({'field': 'severity', 'raw_value': value, 'proposed_value': candidate,
                                 'note': parts[1], 'rule': 'Separate a trailing recommendation from the rating label; requires confirmation.'})
    priority_order = ('Low', 'Moderate', 'High', 'Critical', 'Urgent')
    proposed['priority'] = [v for v in priority_order if v in menus['priority']]

    summary = {
        'reports_read': len(reports), 'primary_reports': sum(r['role'] == 'primary' for r in reports),
        'supporting_documents': sum(r['role'] == 'supporting' for r in reports),
        'primary_reports_with_inspection_tables': sum(r['role'] == 'primary' and bool(r['inspection_tables']) for r in reports),
        'primary_inspection_groups': primary_tables,
        'source_bytes': sum(r['file_bytes'] for r in reports),
        'xml_bytes_read': sum(r['xml_bytes_read'] for r in reports),
        'elapsed_seconds': round(time.perf_counter() - started, 3),
        'description_counts': dict(description_counts),
        'unique_description_counts': {f: len(v) for f, v in description_library.items()},
        'distinct_table_grids': dict(layout_counts),
        'option_counts': {field: len(values) for field, values in menus.items()},
        'errors': errors,
    }
    priority_colors = {}
    for entry in full_options['priority']:
        if entry['primary_occurrences']:
            priority_colors[entry['value']] = {
                'fill': next(iter(entry['fills'])) if len(entry['fills']) == 1 else None,
                'observed_fills': entry['fills'],
                'sources': entry['primary_sources'],
            }
    outputs = {'report_index.json': reports, 'dropdown_options.json': menus,
               'dropdown_sources.json': full_options, 'extraction_summary.json': summary,
               'description_library.json': description_library,
               'proposed_dropdown_options.json': proposed, 'dropdown_review_items.json': review_items,
               'priority_colors.json': priority_colors}
    for name, data in outputs.items():
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'summary': summary, 'menus': menus}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
