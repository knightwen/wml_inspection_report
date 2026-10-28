"""Editable CAL exports. Excel print settings are authoritative for PDF output.

The source workbook supplies the logo, green rule, A4 portrait geometry, and
project-information band. No historical project content or macros are shipped.
"""
from pathlib import Path
import math
import zipfile
from lxml import etree as E
from PIL import Image as PILImage
from report_types import walk_modules

GREEN = '92D050'
INK = '263B34'
FIELDS = [('Project', 'site'), ('Job No.', 'project_number'), ('Location', 'location'),
          ('Rev.', 'revision'), ('Calc. No.', 'report_number'), ('Date', 'report_date'), ('Subject', 'subject')]


def _lines(text, chars=95):
    # Merged Excel cells cannot AutoFit. Bound row height by splitting long
    # text into printable lines rather than clipping text in a giant merged row.
    import textwrap,unicodedata
    lines = []
    for paragraph in str(text).replace('\r\n', '\n').split('\n'):
        for part in textwrap.wrap(paragraph, chars, replace_whitespace=False) or ['']:
            current='';width=0
            for character in part:
                weight=2 if unicodedata.east_asian_width(character) in 'WFA' else 1
                if width+weight>chars and current:lines.append(current);current='';width=0
                current+=character;width+=weight
            lines.append(current)
    return lines


def generate_xlsx(project, photo_path, resources, target):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image
    from openpyxl.worksheet.pagebreak import Break
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.hyperlink import Hyperlink

    book = Workbook()
    book.remove(book.active)
    meta = project['metadata']
    thin = Side(style='thin', color='CAD2CC')

    def value(sheet, row, col, text):
        cell = sheet.cell(row, col, str(text or ''))
        cell.data_type = 's'  # Pasted formulas are report text, never executable formulas.
        cell.font = Font(name='Arial', size=10, color=INK)
        cell.alignment = Alignment(vertical='top', wrap_text=True)
        return cell

    def merged(sheet, row, start, end, text, bold=False, size=10):
        sheet.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)
        cell = value(sheet, row, start, text)
        cell.font = Font(name='Arial', size=size, bold=bold, color=INK)
        return cell

    def sheet(name):
        ws = book.create_sheet(name)
        ws.sheet_view.showGridLines = False
        for col in range(1, 21):
            ws.column_dimensions[get_column_letter(col)].width = 4.7
        for row, pair in enumerate([FIELDS[:2], FIELDS[2:4], FIELDS[4:6]], 1):
            heights=[]
            for (label, key), col in zip(pair, [1, 11]):
                merged(ws, row, col, col+2, label, True)
                merged(ws, row, col+3, col+9, meta.get(key, ''))
                heights.append(len(_lines(meta.get(key,''),40))*15+5)
                for column in range(col,col+10):ws.cell(row,column).border=Border(bottom=thin)
            ws.row_dimensions[row].height = max(30 if row == 1 else 22,*heights)
        merged(ws, 4, 1, 3, 'Subject', True)
        merged(ws, 4, 4, 20, meta.get('subject', ''))
        ws.row_dimensions[4].height = max(22, len(_lines(meta.get('subject', ''), 100))*15)
        for col in range(1, 21):
            ws.cell(5, col).fill = PatternFill('solid', fgColor=GREEN)
        ws.row_dimensions[5].height = 6
        ws.print_title_rows = '1:5'
        ws.page_setup.orientation = 'portrait'
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins.left = 0.945
        ws.page_margins.right = 0.433
        ws.page_margins.top = 1.0
        ws.page_margins.bottom = 0.5
        ws.page_margins.header = 0.2
        ws.page_margins.footer = 0.2
        ws.oddHeader.left.text = '&G'
        ws.oddHeader.right.text = 'CALCULATION REPORT'
        ws.oddHeader.right.font = 'Arial,Bold'
        ws.oddHeader.right.size = 16
        ws.oddFooter.right.text = 'Page &P of &N'
        ws.freeze_panes = 'A6'
        return ws

    def text(ws, row, content):
        for line in _lines(content):
            merged(ws, row, 1, 20, line)
            ws.row_dimensions[row].height = 17
            row += 1
        return row + 1

    cover = sheet('Cover')
    row = 8
    if meta.get('client'):
        merged(cover,row,1,20,'CLIENT',True,11)
        row=text(cover,row+1,meta['client'])+1
    for title, key in [('INTRODUCTION', 'introduction'), ('MATERIAL PROPERTIES', 'materials')]:
        merged(cover, row, 1, 20, title, True, 11)
        row = text(cover, row+2, project['cal_cover'].get(key, '')) + 2
    for label, key, prefix in [('PREPARED BY', 'prepared_by', 'author'), ('REVIEWED BY', 'reviewed_by', 'reviewer')]:
        merged(cover, row, 1, 6, label, True)
        merged(cover, row, 7, 20, meta.get(key, ''), True)
        row = text(cover, row+1, '\n'.join(filter(None, [meta.get(prefix+'_qualifications'), meta.get(prefix+'_title')])))+1
    headers = ['REVISION', 'DATE', 'STATUS', 'DESIGNED', 'CHECKED', 'APPROVED']
    spans = [(1, 2), (3, 5), (6, 11), (12, 14), (15, 17), (18, 20)]
    for title, (start, end) in zip(headers, spans):
        merged(cover, row, start, end, title, True, 8)
    for revision in project['cal_cover']['revisions'] or [{}]:
        row += 1
        for key, (start, end) in zip(['revision','date','status','designed','checked','approved'], spans):
            merged(cover, row, start, end, revision.get(key, ''))
        cover.row_dimensions[row].height = 28
    cover.print_area = f'A1:T{max(35, row+2)}'

    contents = sheet('Contents')
    merged(contents, 7, 1, 20, 'CONTENTS', True, 14)
    report = sheet('Report')
    row = 7
    headings = []
    for index, (number, module) in enumerate(walk_modules(project['modules']), 9):
        if module['page_break'] and row > 7:
            report.row_breaks.append(Break(id=row-1))
        title = number + '  ' + module['title']
        merged(report, row, 1, 20, title, True, 12 if '.' not in number else 11)
        report.row_dimensions[row].height = max(25,len(_lines(title,95))*17+8)
        headings.append({'row': row, 'contents_row': index, 'title': title})
        cell = merged(contents, index, 1, 18, title)
        contents.row_dimensions[index].height=max(18,len(_lines(title,80))*15+4)
        cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'Report'!A{row}")
        # Native Excel conversion replaces this with an actual printed page.
        merged(contents, index, 19, 20, '')
        row += 2
        for block in module['blocks']:
            if block['type'] == 'text':
                row = text(report, row, block['text'])
            elif block['type'] == 'table':
                columns = len(block['rows'][0])
                for ri, data in enumerate(block['rows']):
                    lines=[_lines(entry,max(5,(math.floor((ci+1)*20/columns)-math.floor(ci*20/columns))*5)) for ci,entry in enumerate(data)]
                    for offset in range(0,max(map(len,lines)),15):
                        height=22
                        for ci,cell_lines in enumerate(lines):
                            start=math.floor(ci*20/columns)+1
                            end=math.floor((ci+1)*20/columns)
                            chunk=cell_lines[offset:offset+15]
                            cell=merged(report,row,start,end,'\n'.join(chunk),ri==0)
                            if ri==0:cell.fill=PatternFill('solid',fgColor='E9EFDF')
                            for c in range(start,end+1):report.cell(row,c).border=Border(bottom=thin)
                            height=max(height,len(chunk)*15+6)
                        report.row_dimensions[row].height=height
                        row+=1
                row += 1
            else:
                path = photo_path(block['photo']['id'])
                with PILImage.open(path) as source:
                    width, height = source.size
                image = Image(str(path))
                image.width = min(650*block['width']/100, 460*width/height)
                image.height = image.width*height/width
                report.add_image(image, f'A{row}')
                # One bounded row lets Excel move the whole figure to the next
                # page instead of cutting it at a break between image rows.
                report.row_dimensions[row].height = image.height*0.75 + 8
                row += 1
                if block['photo'].get('caption'):
                    row = text(report, row, block['photo']['caption'])
                row += 1
        row += 1
    if not headings:
        merged(report, row, 1, 20, '')
    contents.print_area = f'A1:T{max(12, 9+len(headings))}'
    report.print_area = f'A1:T{max(8,row)}'
    outline = book.create_sheet('_Outline')
    outline.append(['Report row', 'Contents row', 'Title'])
    for h in headings:
        outline.append([h['row'], h['contents_row'], h['title']])
    outline.sheet_state = 'veryHidden'
    book.save(target)
    _header_logos(target, resources/'wml-logo.png', 3)


def _header_logos(target, logo, count):
    """Add native Excel header pictures, which repeat on every printed page."""
    s = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    p = 'http://schemas.openxmlformats.org/package/2006/relationships'
    ct = 'http://schemas.openxmlformats.org/package/2006/content-types'
    with zipfile.ZipFile(target) as z:
        parts = {n:z.read(n) for n in z.namelist()}
    parts['xl/media/wml-header.png'] = logo.read_bytes()
    types = E.fromstring(parts['[Content_Types].xml'])
    for ext, kind in [('vml','application/vnd.openxmlformats-officedocument.vmlDrawing'), ('png','image/png')]:
        if not any(n.get('Extension') == ext for n in types):
            E.SubElement(types, '{'+ct+'}Default', Extension=ext, ContentType=kind)
    parts['[Content_Types].xml'] = E.tostring(types)
    for index in range(1, count+1):
        file = f'xl/worksheets/sheet{index}.xml'
        relfile = f'xl/worksheets/_rels/sheet{index}.xml.rels'
        rels = E.fromstring(parts[relfile]) if relfile in parts else E.Element('{'+p+'}Relationships', nsmap={None:p})
        rid = 'rIdWmlHeader'
        E.SubElement(rels, '{'+p+'}Relationship', Id=rid, Type=r+'/vmlDrawing', Target=f'../drawings/header{index}.vml')
        parts[relfile] = E.tostring(rels)
        root = E.fromstring(parts[file])
        E.SubElement(root, '{'+s+'}legacyDrawingHF', {'{'+r+'}id':rid})
        parts[file] = E.tostring(root)
        parts[f'xl/drawings/header{index}.vml'] = b'''<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="1"/></o:shapelayout><v:shapetype id="_x0000_t75" coordsize="21600,21600" o:spt="75" o:preferrelative="t" path="m@4@5l@4@11@9@11@9@5xe" filled="f" stroked="f"><v:stroke joinstyle="miter"/><v:formulas><v:f eqn="if lineDrawn pixelLineWidth 0"/><v:f eqn="sum @0 1 0"/><v:f eqn="sum 0 0 @1"/><v:f eqn="prod @2 1 2"/><v:f eqn="prod @3 21600 pixelWidth"/><v:f eqn="prod @3 21600 pixelHeight"/><v:f eqn="sum @0 0 1"/><v:f eqn="prod @6 1 2"/><v:f eqn="prod @7 21600 pixelWidth"/><v:f eqn="sum @8 21600 0"/><v:f eqn="prod @7 21600 pixelHeight"/><v:f eqn="sum @10 21600 0"/></v:formulas><v:path o:extrusionok="f" gradientshapeok="t" o:connecttype="rect"/><o:lock v:ext="edit" aspectratio="t"/></v:shapetype><v:shape id="LH" o:spid="_x0000_s1025" type="#_x0000_t75" style="position:absolute;margin-left:0;margin-top:0;width:42pt;height:44pt;z-index:1"><v:imagedata o:relid="rId1" o:title="WML"/><o:lock v:ext="edit" rotation="t"/></v:shape></xml>'''
        links = E.Element('{'+p+'}Relationships', nsmap={None:p})
        E.SubElement(links, '{'+p+'}Relationship', Id='rId1', Type=r+'/image', Target='../media/wml-header.png')
        parts[f'xl/drawings/_rels/header{index}.vml.rels'] = E.tostring(links)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)


def generate_docx(project, photo_path, resources, target):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.2677), Inches(11.6929)
    section.left_margin, section.right_margin = Inches(.945), Inches(.433)
    section.top_margin, section.bottom_margin = Inches(2.4), Inches(.5)
    section.header_distance = Inches(.2)
    style = document.styles['Normal']
    style.font.name, style.font.size = 'Arial', Pt(10)
    for level in range(1, 7):
        document.styles[f'Heading {level}'].font.color.rgb = RGBColor.from_string(INK)
        document.styles[f'Heading {level}'].font.name = 'Arial'
    header = section.header
    table = header.add_table(rows=1, cols=2, width=Inches(6.89))
    table.cell(0,0).paragraphs[0].add_run().add_picture(str(resources/'wml-logo.png'), width=Inches(.55))
    title = table.cell(0,1).paragraphs[0]
    title.alignment = 2
    run = title.add_run('CALCULATION REPORT');run.bold=True;run.font.size=Pt(16)
    meta = project['metadata']
    info = header.add_table(rows=0, cols=4, width=Inches(6.89))
    info.style = 'Table Grid'
    for pair in [FIELDS[:2], FIELDS[2:4], FIELDS[4:6]]:
        cells = info.add_row().cells
        for (label,key), offset in zip(pair,[0,2]):
            cells[offset].text=label;cells[offset+1].text=meta.get(key,'')
    cells=info.add_row().cells;cells[0].text='Subject';cells[1].merge(cells[3]).text=meta.get('subject','')
    p=header.add_paragraph()
    borders=OxmlElement('w:pBdr');bottom=OxmlElement('w:bottom')
    for k,v in [('val','single'),('sz','16'),('color',GREEN)]:bottom.set(qn('w:'+k),v)
    borders.append(bottom);p._p.get_or_add_pPr().append(borders)
    if meta.get('client'):document.add_paragraph('CLIENT: '+meta['client'])
    for title,key in [('INTRODUCTION','introduction'),('MATERIAL PROPERTIES','materials')]:
        heading=document.add_paragraph();run=heading.add_run(title);run.bold=True;run.font.size=Pt(11)
        document.add_paragraph(project['cal_cover'].get(key,''))
    for label,key,prefix in [('PREPARED BY','prepared_by','author'),('REVIEWED BY','reviewed_by','reviewer')]:
        document.add_paragraph(label+': '+meta.get(key,''))
        document.add_paragraph('\n'.join(filter(None,[meta.get(prefix+'_qualifications'),meta.get(prefix+'_title')])))
    table=document.add_table(rows=1,cols=6);table.style='Table Grid'
    keys=['revision','date','status','designed','checked','approved']
    for c,k in zip(table.rows[0].cells,keys):c.text=k.upper()
    for row in project['cal_cover']['revisions'] or [{}]:
        for c,k in zip(table.add_row().cells,keys):c.text=row.get(k,'')
    document.add_page_break()
    document.add_paragraph('CONTENTS','Title')
    # A visible result is included so the directory is useful before Word updates it.
    p=document.add_paragraph()
    begin=OxmlElement('w:fldChar');begin.set(qn('w:fldCharType'),'begin');p.add_run()._r.append(begin)
    instruction=OxmlElement('w:instrText');instruction.text=' TOC \\o "1-6" \\h \\z \\u ';p.add_run()._r.append(instruction)
    separator=OxmlElement('w:fldChar');separator.set(qn('w:fldCharType'),'separate');p.add_run()._r.append(separator)
    for number,module in walk_modules(project['modules']):
        document.add_paragraph(number+'  '+module['title'])
    end=OxmlElement('w:fldChar');end.set(qn('w:fldCharType'),'end');document.add_paragraph().add_run()._r.append(end)
    document.add_page_break()
    for index,(number,module) in enumerate(walk_modules(project['modules'])):
        if index and module['page_break']:document.add_page_break()
        document.add_heading(number+'  '+module['title'],min(6,number.count('.')+1))
        for block in module['blocks']:
            if block['type']=='text':document.add_paragraph(block['text'])
            elif block['type']=='table':
                table=document.add_table(rows=0,cols=len(block['rows'][0]));table.style='Table Grid'
                for index,row in enumerate(block['rows']):
                    cells=table.add_row().cells
                    for cell,entry in zip(cells,row):cell.text=entry
                    if index==0:
                        repeat=OxmlElement('w:tblHeader');table.rows[0]._tr.get_or_add_trPr().append(repeat)
            else:
                image_path=photo_path(block['photo']['id'])
                with PILImage.open(image_path) as image:w,h=image.size
                width=min(6.89*block['width']/100,6.5*w/h)
                document.add_picture(str(image_path),width=Inches(width))
                if block['photo'].get('caption'):document.add_paragraph(block['photo']['caption'],'Caption')
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE')
    footer=section.footer.paragraphs[0];footer.alignment=2;footer._p.append(field)
    document.save(target)
