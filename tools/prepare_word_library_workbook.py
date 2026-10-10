"""Prepare editable library rows, review candidates, and unmodified source records."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'analysis'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def key(text):
    text = unicodedata.normalize('NFKC', text).casefold().replace('\u2019', "'")
    text = re.sub(r'(?m)^\s*[\u2013\u2014\u2022-]\s*', '', text)
    return ' '.join(re.findall(r'(?<![a-z0-9])[+-]?\d+(?:\.\d+)*|[a-z]+(?:\x27[a-z]+)?|[%<>=+/]', text))


reports = load('report_index.json')
groups = load('description_format_cleaned_candidates.json')
pairs = load('description_near_duplicate_pairs.json')
locations = load('description_location_candidates.json')
blocks = load('description_common_action_blocks.json')
synonyms = load('description_synonym_examples.json')
source_ids = {r['source']: f'SRC-{i:03d}' for i, r in enumerate(reports, 1)}
ids, lookup = {}, {}
for field, items in groups.items():
    prefix = 'OBS' if field == 'observation' else 'REC'
    ids[field] = {}
    lookup[field] = {}
    for i, item in enumerate(items, 1):
        item_id = f'{prefix}-{i:04d}'
        ids[field][key(item['text'])] = item_id
        lookup[field][item_id] = item


def source_refs(values):
    return ', '.join(source_ids[v] for v in sorted(set(values)))


review, related, review_details = [], defaultdict(list), []


def add_review(field, method, text_a, text_b, item_ids, suggestion, reason, variables='', source_values=()):
    review_id = f'MRG-{len(review) + 1:04d}'
    full_text_b = text_b
    text_b = text_b.split('\n\n')[0]
    if '\n\n' in full_text_b:
        reason += ' 其余完整描述见确认项明细。'
    review.append([review_id, 'Observation' if field == 'observation' else 'Recommendation',
                   '待确认', suggestion, method, reason, ', '.join(item_ids), text_a, text_b,
                   variables, '', source_refs(source_values)])
    for item_id in item_ids:
        related[item_id].append(review_id)
        item = lookup[field][item_id]
        review_details.append([review_id, 'Observation' if field == 'observation' else 'Recommendation',
                               item_id, item['text'], item['occurrences'], source_refs(item['sources'])])


for field in ('observation', 'recommendation'):
    # All near matches remain independent in the candidate library.
    for pair in pairs[field]:
        item_ids = [ids[field][key(pair['left'])], ids[field][key(pair['right'])]]
        warnings = pair['warnings']
        reason = '措辞近似，需确认含义和适用范围是否一致。'
        suggestion = pair['left'] if pair['left_occurrences'] >= pair['right_occurrences'] else pair['right']
        method, variables = '近似描述核对', ''
        if warnings:
            suggestion = ''
            reason = '程度、范围、处理方法、条件或编号存在差异，建议保持独立；如仅编号不同可改为模板。'
        if any('numeric' in w for w in warnings):
            reason += ' 数值或章节引用需保留。'
        if not warnings and {'discoloration', 'discolouration'} <= {s.lower() for s in re.findall(r'discolou?ration', pair['left'] + ' ' + pair['right'], re.I)}:
            suggestion = next(t for t in (pair['left'], pair['right']) if 'discolouration' in t.lower())
            reason = '美式与澳式拼写不同，建议统一为 discolouration。'
        add_review(field, method, pair['left'], pair['right'], item_ids, suggestion, reason,
                   variables, pair['left_sources'] + pair['right_sources'])

for items in locations:
    item_ids = [ids['observation'][key(item['original'])] for item in items]
    suggestion = '{location}. ' + items[0]['core_description']
    add_review('observation', '位置模板', items[0]['original'],
               '\n\n'.join(x['original'] for x in items[1:]), item_ids, suggestion,
               '核心现象相同，仅开头位置不同。可把位置单独填写；生成报告时须保留位置。',
               'location：现场位置', [s for x in items for s in x['sources']])

salt = [g for g in synonyms['salt_staining_cleanup'] if not re.search(r'\ball\b', g['text'], re.I)]
if len(salt) > 1:
    add_review('recommendation', '同义表达核对', salt[0]['text'],
               '\n\n'.join(g['text'] for g in salt[1:]),
               [ids['recommendation'][key(g['text'])] for g in salt], 'Remove salt staining.',
               '清除盐渍的措辞不同，可考虑统一。含 all 或附加处理措施的建议仍单独保留。',
               '', [s for g in salt for s in g['sources']])

for block in blocks:
    pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
    applicable = [g for g in groups['recommendation']
                  if key(block['text']) in {key(sentence) for sentence in pattern.split(g['text'])}]
    item_ids = [ids['recommendation'][key(g['text'])] for g in applicable]
    add_review('recommendation', '提取复用短句', block['text'],
               '\n\n'.join(g['text'] for g in applicable), item_ids, block['text'],
               '可把此句做成复用措施。仅提取短句，完整建议中的其他措施、条件和引用均须保留。',
               '', block['sources'])

element_counts = defaultdict(Counter)
for report in reports:
    if report['role'] != 'primary':
        continue
    for table in report['inspection_tables']:
        for record in table['records']:
            for field in ('observation', 'recommendation'):
                if record[field]:
                    item_id = ids[field][key(record[field])]
                    element_counts[item_id][table['fields']['element']] += 1

library_rows = {}
for field, items in groups.items():
    rows = []
    for item in items:
        item_id = ids[field][key(item['text'])]
        common_elements = '; '.join(name for name, _ in element_counts[item_id].most_common(3))
        rows.append([item_id, '是', item['text'], common_elements, item['occurrences'],
                     len(item['original_variants']), ', '.join(related[item_id]),
                     source_refs(item['sources']), ''])
    library_rows[field] = rows

raw_rows, raw_counts = [], Counter()
for report in reports:
    for table in report['inspection_tables']:
        for record in table['records']:
            for field in ('observation', 'recommendation'):
                text = record[field]
                if not text:
                    continue
                raw_counts[(report['role'], field)] += 1
                raw_rows.append([f'RAW-{len(raw_rows)+1:05d}',
                                 'Observation' if field == 'observation' else 'Recommendation',
                                 text, table['fields']['element'], source_ids[report['source']],
                                 ids[field].get(key(text), ''),
                                 '正式报告' if report['role'] == 'primary' else '审阅或辅助文档',
                                 table['table'], record['row'], record['photo_count'],
                                 table['fields'].get('condition_rating', ''),
                                 table['fields'].get('likelihood', ''), table['fields'].get('severity', ''),
                                 table['fields'].get('priority', '')])

source_rows = [[source_ids[r['source']], '正式报告' if r['role']=='primary' else '审阅或辅助文档',
                Path(r['source']).name, r['source'], len(r['inspection_tables'])] for r in reports]

assert len(library_rows['observation']) == 622
assert len(library_rows['recommendation']) == 175
assert raw_counts[('primary', 'observation')] == 791
assert raw_counts[('primary', 'recommendation')] == 505
assert len(raw_rows) == 1951
assert sum(r[4] for r in library_rows['observation']) == 791
assert sum(r[4] for r in library_rows['recommendation']) == 505
assert all(set(r[6].split(', ')) <= set(lookup['observation']) | set(lookup['recommendation']) for r in review)

payload = {'library': library_rows, 'review': review, 'review_details': review_details, 'raw': raw_rows, 'sources': source_rows,
           'counts': {'observation': 622, 'recommendation': 175, 'review': len(review), 'raw': len(raw_rows),
                      'primary_observations': 791, 'primary_recommendations': 505, 'sources': len(source_rows),
                      'primary_sources': sum(r['role']=='primary' for r in reports)},
           'review_methods': dict(Counter(r[4] for r in review))}
(DATA / 'word_library_workbook_data.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'counts':payload['counts'],'review_methods':payload['review_methods']},ensure_ascii=True,indent=2))
