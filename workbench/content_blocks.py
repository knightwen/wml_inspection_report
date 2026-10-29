"""Shared bounded report content, including legacy text-only chapters."""
import re
import secrets

SECTION_KEYS = ('introduction', 'remedial_works', 'conclusion', 'cost_estimate')


def text_block(text):
    return {'id': secrets.token_hex(16), 'type': 'text', 'text': text}


def cover_modules(project):
    cover = project['cal_cover']
    if 'modules' in cover:
        return cover['modules']
    return [{'id': secrets.token_hex(16), 'title': cover.get(key+'_title', default),
             'blocks': [text_block(cover[key])] if cover.get(key) else []}
            for key, default in [('introduction', 'INTRODUCTION'), ('materials', 'MATERIAL PROPERTIES')]]


def section_blocks(project, key):
    blocks = project.get('section_blocks', {})
    return blocks[key] if key in blocks else ([text_block(project['sections'][key])] if project.get('sections', {}).get(key) else [])


def content_photos(project):
    if project.get('template_id') == 'calculation':
        groups = [m['blocks'] for m in cover_modules(project)]
    else:
        groups = project.get('section_blocks', {}).values()
    for blocks in groups:
        for block in blocks:
            if block['type'] == 'image':
                yield block['photo']


def validate_blocks(blocks, catalog, seen=None):
    seen = set() if seen is None else seen
    if not isinstance(blocks, list) or len(blocks) > 1000:
        raise ValueError('内容块格式不正确或过多 / Invalid or excessive content blocks')
    def string(value, maximum):
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError('报告内容格式不正确或过长 / Invalid or oversized report content')
    for block in blocks:
        if not isinstance(block, dict):raise ValueError('内容块格式不正确 / Invalid content block')
        bid = block.get('id')
        if not isinstance(bid, str) or not re.fullmatch(r'[a-f0-9]{32}', bid) or bid in seen:
            raise ValueError('模块或内容编号无效或重复 / Invalid or duplicate content ID')
        seen.add(bid)
        if block.get('type') == 'text':string(block.get('text'), 60000)
        elif block.get('type') == 'table':
            rows = block.get('rows')
            if not isinstance(rows, list) or not 1 <= len(rows) <= 200:raise ValueError('表格需要 1–200 行 / Tables need 1–200 rows')
            columns = len(rows[0]) if isinstance(rows[0], list) else 0
            if not 1 <= columns <= 20:raise ValueError('表格需要 1–20 列 / Tables need 1–20 columns')
            for row in rows:
                if not isinstance(row, list) or len(row) != columns:raise ValueError('表格列数不一致 / Inconsistent table columns')
                for cell in row:string(cell, 2000)
        elif block.get('type') == 'image':
            photo = block.get('photo')
            if not isinstance(photo, dict) or photo.get('id') not in catalog:raise ValueError('照片不存在 / Image not found')
            photo['name'] = catalog[photo['id']]['name']
            string(photo.get('caption', ''), 200)
            if type(block.get('width')) is not int or not 20 <= block['width'] <= 100:raise ValueError('图片宽度须为 20–100% / Image width must be 20–100%')
        else:raise ValueError('不支持的内容块 / Unsupported content block')


def validate_sections(project, catalog):
    sections = project.get('section_blocks', {})
    if not isinstance(sections, dict) or set(sections) - set(SECTION_KEYS):
        raise ValueError('报告章节格式不正确 / Invalid report chapters')
    seen = set()
    for blocks in sections.values():validate_blocks(blocks, catalog, seen)
