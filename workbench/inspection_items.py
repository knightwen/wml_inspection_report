"""Inspection items share ratings; each subitem owns its photos and wording."""
import secrets

RATING_FIELDS = ['element', 'condition_rating', 'likelihood', 'severity', 'priority']
CONTENT_FIELDS = ['photos', 'observation', 'recommendation', 'observation_source', 'recommendation_source']


def blank_subitem():
    return {'id': secrets.token_hex(16), 'photos': [], 'observation': '', 'recommendation': ''}


def blank_item():
    return {**dict.fromkeys(RATING_FIELDS, ''), 'subitems': [blank_subitem()]}


def item_subitems(item):
    # Direct exports of older snapshots remain supported as well as migrated drafts.
    if 'subitems' in item:
        return item['subitems']
    return [{key: item.get(key, [] if key == 'photos' else '') for key in CONTENT_FIELDS}]


def normalize_project(project):
    if not isinstance(project.get('items'), list):
        raise ValueError('草稿格式不正确')
    for item in [*project.get('items', []), project.get('editor', {})]:
        if not isinstance(item, dict):
            raise ValueError('检查项格式不正确')
        if 'subitems' not in item:
            group = blank_subitem()
            group.update({key: item[key] for key in CONTENT_FIELDS if key in item})
            item['subitems'] = [group]
        for key in CONTENT_FIELDS:
            item.pop(key, None)
        if isinstance(item['subitems'], list):
            for group in item['subitems']:
                if isinstance(group, dict):
                    for key in ['photos', 'observation', 'recommendation']:
                        group.setdefault(key, [] if key == 'photos' else '')
    project['schema_version'] = 2
    return project


def all_photos(item):
    return [photo for group in item_subitems(item) for photo in group['photos']]
