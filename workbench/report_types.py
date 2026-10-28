"""Report-type registry and bounded, per-draft calculation report content."""
import re
import secrets

REPORT_TYPES = [
    {'id': 'inspection', 'name': 'Inspection Report', 'formats': ['docx']},
    {'id': 'calculation', 'name': 'Calculation Report', 'formats': ['xlsx', 'docx', 'pdf']},
]
ID = re.compile(r'^[a-f0-9]{32}$')
DEFAULT_MODULES = [
    ('References', []), ('Design Criteria', []),
    ('Load Engineering', [('Load Cases', []), ('Load Combinations', []), ('Load Inputs', [])]),
    ('Analysis Results', [('Strength', []), ('Serviceability', [])]),
]


def report_type(project):
    return project.get('template_id', 'inspection')


def new_modules(definitions=None):
    return [{'id': secrets.token_hex(16), 'title': title, 'page_break': False,
             'blocks': [], 'children': new_modules(children)}
            for title, children in (DEFAULT_MODULES if definitions is None else definitions)]


def walk_modules(modules, prefix=()):
    for index, module in enumerate(modules, 1):
        number = (*prefix, index)
        yield '.'.join(map(str, number)), module
        yield from walk_modules(module['children'], number)


def calculation_photos(project):
    for _, module in walk_modules(project.get('modules', [])):
        for block in module['blocks']:
            if block['type'] == 'image':
                yield block['photo']


def validate_calculation(project, catalog):
    """Validate before storing/exporting/importing; never execute cell content."""
    seen = set()
    def identity(value):
        if not isinstance(value, str) or not ID.fullmatch(value) or value in seen:
            raise ValueError('模块或内容编号无效或重复 / Invalid or duplicate content ID')
        seen.add(value)
    def string(value, limit):
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('报告内容格式不正确或过长 / Invalid or oversized report content')
    count = 0
    block_count = 0
    def modules(nodes, depth=1):
        nonlocal count, block_count
        if not isinstance(nodes, list) or depth > 6:
            raise ValueError('章节最多六级 / Maximum six chapter levels')
        for module in nodes:
            count += 1
            if count > 200 or not isinstance(module, dict):
                raise ValueError('最多 200 个章节 / Maximum 200 chapters')
            identity(module.get('id'))
            string(module.get('title'), 500)
            if not module['title'].strip() or type(module.get('page_break')) is not bool:
                raise ValueError('请填写章节标题 / A chapter title is required')
            blocks = module.get('blocks')
            if not isinstance(blocks, list):
                raise ValueError('内容块格式不正确 / Invalid content blocks')
            for block in blocks:
                block_count += 1
                if block_count > 1000 or not isinstance(block, dict):
                    raise ValueError('最多 1000 个内容块 / Maximum 1000 content blocks')
                identity(block.get('id'))
                kind = block.get('type')
                if kind == 'text':
                    string(block.get('text'), 60000)
                elif kind == 'table':
                    rows = block.get('rows')
                    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
                        raise ValueError('表格需要 1–200 行 / Tables need 1–200 rows')
                    columns = len(rows[0]) if isinstance(rows[0], list) else 0
                    if not 1 <= columns <= 20:
                        raise ValueError('表格需要 1–20 列 / Tables need 1–20 columns')
                    for row in rows:
                        if not isinstance(row, list) or len(row) != columns:
                            raise ValueError('表格列数不一致 / Inconsistent table columns')
                        for cell in row:
                            string(cell, 2000)
                elif kind == 'image':
                    photo = block.get('photo')
                    if not isinstance(photo, dict) or photo.get('id') not in catalog:
                        raise ValueError('照片不存在 / Image not found')
                    photo['name'] = catalog[photo['id']]['name']
                    string(photo.get('caption', ''), 200)
                    if type(block.get('width')) is not int or not 20 <= block['width'] <= 100:
                        raise ValueError('图片宽度须为 20–100% / Image width must be 20–100%')
                else:
                    raise ValueError('不支持的内容块 / Unsupported content block')
            modules(module.get('children'), depth + 1) if module.get('children') else None
            if not isinstance(module.get('children'), list):
                raise ValueError('子章节格式不正确 / Invalid subchapters')
    modules(project.get('modules'))
    cover = project.get('cal_cover')
    if not isinstance(cover, dict):
        raise ValueError('封面格式不正确 / Invalid cover')
    for key in ['introduction', 'materials']:
        string(cover.get(key, ''), 60000)
    for key in ['title','introduction_title','materials_title']:
        if key in cover:string(cover[key],120)
    revisions = cover.get('revisions')
    if not isinstance(revisions, list) or len(revisions) > 100:
        raise ValueError('修订记录格式不正确 / Invalid revision history')
    for row in revisions:
        if not isinstance(row, dict):
            raise ValueError('修订记录格式不正确 / Invalid revision history')
        for key in ['revision', 'date', 'status', 'designed', 'checked', 'approved']:
            string(row.get(key, ''), 500)
