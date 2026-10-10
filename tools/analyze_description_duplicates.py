"""Audit wording reuse without changing the extracted library or source reports."""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'analysis'
LIBRARY = json.loads((OUTPUT / 'description_library.json').read_text(encoding='utf-8'))


def presentation_text(text):
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'(?m)^\s*[\u2013\u2014\u2022-]\s*', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def words(text):
    text = presentation_text(text).casefold().replace('\u2019', "'")
    # Keep decimals, percentages and comparison symbols; never remove technical thresholds.
    return re.findall(r'(?<![a-z0-9])[+-]?\d+(?:\.\d+)*|[a-z]+(?:\x27[a-z]+)?|[%<>=+/]', text)


def format_key(text):
    return ' '.join(words(text))


def qualifiers(text):
    tokens = set(words(text))
    protected = {'no', 'not', 'none', 'without', 'minor', 'moderate', 'major', 'severe',
                 'significant', 'good', 'all', 'some', 'local', 'localised', 'localized',
                 'if', 'until', 'prior', 'may', 'must', 'shall', 'inspect', 'investigate',
                 'monitor', 'replace', 'replacement', 'repaint', 'galvanise', 'galvanising',
                 'bitumen', 'close', 'closed', 'remove', 'repair'}
    return sorted(tokens & protected)


def location_split(text):
    """Separate explicit opening location sentences only; never discard their information."""
    text = presentation_text(text)
    first, separator, rest = text.partition('. ')
    location = re.match(
        r'^(?:(?:left|right)[ -]hand side\b|(?:front|back) of (?:the )?(?:property|house)\b|'
        r'(?:front|back) wall\b|side overhang\b)', first, flags=re.I)
    if separator and location and not re.search(
        r'\b(?:corrosion|corroded|crack|cracked|deterioration|staining|damaged|condition)\b', first, re.I):
        return first, rest
    return None


audit, proposed, examples = {}, {}, {}
for field, entries in LIBRARY.items():
    buckets = defaultdict(list)
    for entry in entries:
        buckets[format_key(entry['text'])].append(entry)
    groups = []
    for bucket in buckets.values():
        representative = max(bucket, key=lambda e: e['occurrences'])
        groups.append({
            'text': presentation_text(representative['text']),
            'occurrences': sum(e['occurrences'] for e in bucket),
            'elements': sorted({x for e in bucket for x in e['elements']}),
            'sources': sorted({x for e in bucket for x in e['sources']}),
            'original_variants': [{'text': e['text'], 'occurrences': e['occurrences']} for e in bucket],
        })
    groups.sort(key=lambda g: (-g['occurrences'], g['text']))
    proposed[field] = groups
    total = sum(e['occurrences'] for e in entries)
    audit[field] = {
        'record_occurrences': total, 'unique_before_format_cleanup': len(entries),
        'repeat_occurrences': total - len(entries),
        'repeat_percentage': round((total - len(entries)) / total * 100, 1),
        'unique_after_format_cleanup': len(groups),
        'additional_format_only_reduction': len(entries) - len(groups),
        'format_variant_groups': sum(len(g['original_variants']) > 1 for g in groups),
        'top_5_record_coverage': round(sum(g['occurrences'] for g in groups[:5]) / total * 100, 1),
        'top_10_record_coverage': round(sum(g['occurrences'] for g in groups[:10]) / total * 100, 1),
    }
    examples[field] = [g for g in groups if len(g['original_variants']) > 1]

near_pairs = {}
for field, groups in proposed.items():
    pairs = []
    token_sets = [set(words(g['text'])) for g in groups]
    keys = [format_key(g['text']) for g in groups]
    for left in range(len(groups)):
        for right in range(left + 1, len(groups)):
            a, b = token_sets[left], token_sets[right]
            if not a or not b or len(a & b) / len(a | b) < 0.55:
                continue
            ratio = SequenceMatcher(None, keys[left], keys[right]).ratio()
            if ratio < 0.84:
                continue
            one, two = groups[left], groups[right]
            warnings = []
            if qualifiers(one['text']) != qualifiers(two['text']):
                warnings.append('Different condition, scope, action, material or conditional wording.')
            numbers_a = [t for t in words(one['text']) if re.match(r'^[+-]?\d', t) or t in ('%', '<', '>', '=')]
            numbers_b = [t for t in words(two['text']) if re.match(r'^[+-]?\d', t) or t in ('%', '<', '>', '=')]
            if numbers_a != numbers_b:
                warnings.append('Different numeric values, thresholds or section references.')
            pairs.append({'left': one['text'], 'right': two['text'],
                          'similarity': round(ratio, 3), 'warnings': warnings,
                          'left_occurrences': one['occurrences'], 'right_occurrences': two['occurrences'],
                          'left_sources': one['sources'], 'right_sources': two['sources'],
                          'decision': 'Review only; similarity does not establish equivalence.'})
    pairs.sort(key=lambda p: (-p['similarity'], p['left'], p['right']))
    near_pairs[field] = pairs
    audit[field]['near_duplicate_pairs_for_review'] = len(pairs)
    audit[field]['near_pairs_with_protected_word_differences'] = sum(bool(p['warnings']) for p in pairs)

location_buckets = defaultdict(list)
for entry in proposed['observation']:
    split = location_split(entry['text'])
    if split:
        location, core = split
        location_buckets[format_key(core)].append({
            'location': location, 'core_description': core, 'original': entry['text'],
            'occurrences': entry['occurrences'], 'sources': entry['sources'],
        })
location_groups = [items for items in location_buckets.values()
                   if len({format_key(x['location']) for x in items}) > 1]
location_groups.sort(key=lambda items: (-sum(x['occurrences'] for x in items), items[0]['core_description']))
audit['location_parameter_candidates'] = {
    'matching_groups': len(location_groups),
    'distinct_descriptions_in_groups': sum(len(g) for g in location_groups),
    'potential_additional_option_reduction': sum(len(g) - 1 for g in location_groups),
    'note': 'Keep the location in a separate editable field; never omit it from the generated report.',
}

sentence_buckets = {}
for entry in proposed['recommendation']:
    # Preserve an exact sentence and its provenance; compositional suggestions are not merged instructions.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', entry['text'])
    seen = set()
    for sentence in sentences:
        key = format_key(sentence)
        if key in seen:
            continue
        seen.add(key)
        bucket = sentence_buckets.setdefault(key, {'text': sentence, 'record_occurrences': 0,
                                                    'distinct_descriptions': 0, 'sources': set()})
        bucket['record_occurrences'] += entry['occurrences']
        bucket['distinct_descriptions'] += 1
        bucket['sources'].update(entry['sources'])
common_sentences = [{**b, 'sources': sorted(b['sources'])} for b in sentence_buckets.values()
                    if b['distinct_descriptions'] > 1]
common_sentences.sort(key=lambda b: (-b['record_occurrences'], b['text']))
audit['recommendation']['repeated_sentence_blocks'] = len(common_sentences)

synonym_examples = {
    'salt_staining_cleanup': [e for e in proposed['recommendation']
                             if re.fullmatch(r'(?:Remove|Clean(?: off)?)(?: all)? salt staining\.?', e['text'], re.I)],
    'no_remedial_action': [e for e in proposed['recommendation']
                          if re.fullmatch(r'(?:None|None required|No (?:remedial|remediation) (?:works |action )?required)\.?', e['text'], re.I)],
}

outputs = {
    'description_dedup_analysis.json': audit,
    'description_format_cleaned_candidates.json': proposed,
    'description_format_variants.json': examples,
    'description_near_duplicate_pairs.json': near_pairs,
    'description_location_candidates.json': location_groups,
    'description_common_action_blocks.json': common_sentences,
    'description_synonym_examples.json': synonym_examples,
}
for name, data in outputs.items():
    (OUTPUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(audit, ensure_ascii=True, indent=2))
for field in ('observation', 'recommendation'):
    print('FORMAT_VARIANTS', field)
    for group in examples[field][:8]:
        print(json.dumps({k:v for k,v in group.items() if k not in ('sources','elements')}, ensure_ascii=True))
    print('NEAR_PAIRS', field)
    for pair in near_pairs[field][:12]:
        print(json.dumps({k: v for k, v in pair.items() if not k.endswith('_sources')}, ensure_ascii=True))
print('LOCATION_GROUPS')
for group in location_groups[:5]:
    print(json.dumps([{k: v for k, v in x.items() if k != 'sources'} for x in group], ensure_ascii=True))
print('COMMON_ACTION_BLOCKS')
for item in common_sentences[:10]:
    print(json.dumps({k:v for k,v in item.items() if k != 'sources'}, ensure_ascii=True))
