"""Editable CAL exports. Excel print settings are authoritative for PDF output.

The source workbook supplies the logo, green rule, A4 portrait geometry, and
project-information band. No historical project content or macros are shipped.
"""
import math
from PIL import Image as PILImage
from report_types import walk_modules
from content_blocks import cover_modules

GREEN = '92D050'
INK = '263B34'
CONTENT_ROW = 11
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
    thin = Side(style='thin', color='59635D')

    def outline(sheet, row, start, end):
        # Border the logical merged cell, not its individual backing columns.
        for col in range(start,end+1):
            sheet.cell(row,col).border=Border(top=thin,bottom=thin,
                left=thin if col==start else Side(),right=thin if col==end else Side())

    def value(sheet, row, col, text):
        cell = sheet.cell(row, col, str(text or ''))
        cell.data_type = 's'  # Pasted formulas are report text, never executable formulas.
        cell.font = Font(name='Arial', size=10, color=INK)
        cell.alignment = Alignment(vertical='top', wrap_text=True)
        return cell

    def merged(sheet, row, start, end, text, bold=False, size=10, bordered=False):
        sheet.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)
        cell = value(sheet, row, start, text)
        cell.font = Font(name='Arial', size=size, bold=bold, color=INK)
        if bordered:outline(sheet,row,start,end)
        return cell

    def sheet(name):
        ws = book.create_sheet(name)
        ws.sheet_view.showGridLines = False
        ws.sheet_view.view = 'normal'
        for col in range(1, 21):
            ws.column_dimensions[get_column_letter(col)].width = 4.7
        # Keep branding in worksheet cells/drawings so it is visible and editable
        # in normal Excel view. Excel also repeats these drawings with print titles.
        logo=Image(str(resources/'wml-logo-horizontal.png'));logo.width=205;logo.height=71
        ws.add_image(logo,'A1')
        ws.merge_cells('K1:T3')
        title=value(ws,1,11,project['cal_cover'].get('title','CALCULATION REPORT'))
        title.font=Font(name='Arial',size=16,bold=True,color=INK)
        title.alignment=Alignment(horizontal='right',vertical='center',wrap_text=True)
        band=max(62,len(_lines(str(title.value or ''),55))*20+6)
        for row in range(1,4):ws.row_dimensions[row].height=band/3
        for col in range(1,21):ws.cell(4,col).fill=PatternFill('solid',fgColor=GREEN)
        ws.row_dimensions[4].height=10
        for row, pair in enumerate([FIELDS[:2], FIELDS[2:4], FIELDS[4:6]], 5):
            heights=[]
            for (label, key), col in zip(pair, [1, 11]):
                merged(ws, row, col, col+1, label, False, size=9)
                merged(ws, row, col+2, col+9, meta.get(key, ''), size=9)
                heights.append(len(_lines(meta.get(key,''),46))*12+4)
            ws.row_dimensions[row].height = max(18,*heights)
            for col in range(1,21):ws.cell(row,col).border=Border(bottom=Side(style='thin',color='C9C9C9'))
        merged(ws, 8, 1, 2, 'Subject', size=9)
        merged(ws, 8, 3, 20, meta.get('subject', ''), size=9)
        for col in range(1,21):ws.cell(8,col).border=Border(bottom=Side(style='thin',color='C9C9C9'))
        ws.row_dimensions[8].height = max(18, len(_lines(meta.get('subject', ''), 100))*12+4)
        ws.row_dimensions[9].height=8
        ws.print_title_rows = '1:9'
        ws.page_setup.orientation = 'portrait'
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins.left = 0.945
        ws.page_margins.right = 0.433
        ws.page_margins.top = 0.433
        ws.page_margins.bottom = 0.5
        ws.page_margins.header = 0.2
        ws.page_margins.footer = 0.2
        ws.oddFooter.right.text = 'Page &P of &N'
        ws.freeze_panes = 'A10'
        return ws

    def text(ws, row, content):
        for line in _lines(content):
            merged(ws, row, 1, 20, line)
            ws.row_dimensions[row].height = 17
            row += 1
        return row + 1

    def write_blocks(ws, row, blocks):
        for block in blocks:
            if block['type'] == 'text':
                row = text(ws, row, block['text'])
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
                            cell=merged(ws,row,start,end,'\n'.join(chunk),ri==0,bordered=True)
                            if ri==0:cell.fill=PatternFill('solid',fgColor='E9EFDF')
                            height=max(height,len(chunk)*15+6)
                        ws.row_dimensions[row].height=height
                        row+=1
                row += 1
            else:
                path = photo_path(block['photo']['id'])
                with PILImage.open(path) as source:
                    width, height = source.size
                image = Image(str(path))
                image.width = min(650*block['width']/100, 460*width/height)
                image.height = image.width*height/width
                ws.add_image(image, f'A{row}')
                # One bounded row lets Excel move the whole figure to the next
                # page instead of cutting it at a break between image rows.
                ws.row_dimensions[row].height = image.height*0.75 + 8
                row += 1
                if block['photo'].get('caption'):
                    row = text(ws, row, block['photo']['caption'])
                row += 1
        return row

    cover = sheet('Cover')
    cover.page_setup.fitToHeight = 1
    row = CONTENT_ROW
    if meta.get('client'):
        merged(cover,row,1,20,'CLIENT',True,11)
        row=text(cover,row+1,meta['client'])+1
    modules=cover_modules(project)
    for index,module in enumerate(modules):
        start=row
        for col in range(1,21):cover.cell(row,col).border=Border(top=Side(style='thin',color='000000'))
        if module['title']:
            merged(cover, row, 1, 20, module['title'], True, 11)
            cover.row_dimensions[row].height=max(20,len(_lines(module['title'],95))*16+4)
            row += 2
        row = write_blocks(cover, row, module['blocks']) + 2
        row=max(row,start+([6,10,7][index] if len(modules)==3 else 8))
    row+=2
    while sum(cover.row_dimensions[r].height or 15 for r in range(1,row))<480:row+=1
    for label, key, prefix in [('PREPARED BY:', 'prepared_by', 'author'), ('REVIEWED BY:', 'reviewed_by', 'reviewer')]:
        merged(cover,row,1,3,label,True,9)
        merged(cover,row,4,20,meta.get(key,''),True,9)
        details='\n'.join(filter(None,[meta.get(prefix+'_qualifications'),meta.get(prefix+'_title')]))
        merged(cover,row+1,4,20,details,size=9)
        cover.row_dimensions[row+1].height=max(22,len(_lines(details,90))*12)
        row+=4
    headers = ['REVISION', 'DATE', 'STATUS', 'DESIGNED', 'CHECKED', 'APPROVED']
    spans = [(1, 2), (3, 5), (6, 11), (12, 14), (15, 17), (18, 20)]
    for title, (start, end) in zip(headers, spans):
        merged(cover, row, start, end, title, True, 8, bordered=True)
    for revision in (project['cal_cover']['revisions']+[{}]*max(0,4-len(project['cal_cover']['revisions']))):
        row += 1
        for key, (start, end) in zip(['revision','date','status','designed','checked','approved'], spans):
            merged(cover, row, start, end, revision.get(key, ''), bordered=True)
        cover.row_dimensions[row].height = 14
    cover.print_area = f'A1:T{row}'

    contents = sheet('Contents')
    merged(contents, CONTENT_ROW, 1, 20, 'CONTENTS', True, 14)
    report = sheet('Report')
    row = CONTENT_ROW
    headings = []
    for index, (number, module) in enumerate(walk_modules(project['modules']), CONTENT_ROW+2):
        if module['page_break'] and row > CONTENT_ROW:
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
        row = write_blocks(report, row, module['blocks'])
        row += 1
    if not headings:
        merged(report, row, 1, 20, '')
    contents.print_area = f'A1:T{max(CONTENT_ROW+4, CONTENT_ROW+2+len(headings))}'
    report.print_area = f'A1:T{max(CONTENT_ROW+1,row)}'
    outline = book.create_sheet('_Outline')
    outline.append(['Report row', 'Contents row', 'Title'])
    for h in headings:
        outline.append([h['row'], h['contents_row'], h['title']])
    outline.sheet_state = 'veryHidden'
    book.save(target)



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
    table.cell(0,0).paragraphs[0].add_run().add_picture(str(resources/'wml-logo-horizontal.png'), width=Inches(2.45))
    title = table.cell(0,1).paragraphs[0]
    title.alignment = 2
    run = title.add_run(project['cal_cover'].get('title','CALCULATION REPORT'));run.bold=True;run.font.size=Pt(16)
    meta = project['metadata']
    p=header.add_paragraph()
    borders=OxmlElement('w:pBdr');bottom=OxmlElement('w:bottom')
    for k,v in [('val','single'),('sz','56'),('color',GREEN)]:bottom.set(qn('w:'+k),v)
    borders.append(bottom);p._p.get_or_add_pPr().append(borders)
    info = header.add_table(rows=0, cols=4, width=Inches(6.89))
    info.autofit=False
    for cell,width in zip(info.columns,[.8,2.65,.8,2.64]):cell.width=Inches(width)
    for pair in [FIELDS[:2], FIELDS[2:4], FIELDS[4:6]]:
        cells = info.add_row().cells
        for (label,key), offset in zip(pair,[0,2]):
            cells[offset].text=label;cells[offset+1].text=meta.get(key,'')
    cells=info.add_row().cells;cells[0].text='Subject';cells[1].merge(cells[3]).text=meta.get('subject','')
    for row in info.rows:
        for cell in row.cells:
            borders=OxmlElement('w:tcBorders');bottom=OxmlElement('w:bottom')
            for key,value in [('val','single'),('sz','4'),('color','C9C9C9')]:bottom.set(qn('w:'+key),value)
            borders.append(bottom)
            properties=cell._tc.get_or_add_tcPr()
            if properties.find(qn('w:tcBorders')) is None:properties.append(borders)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(2)
                for run in p.runs:run.font.size=Pt(9)

    def write_blocks(blocks, host=document):
        for block in blocks:
            if block['type']=='text':host.add_paragraph(block['text'])
            elif block['type']=='table':
                table=host.add_table(rows=0,cols=len(block['rows'][0]));table.style='Table Grid'
                for index,row in enumerate(block['rows']):
                    cells=table.add_row().cells
                    for cell,entry in zip(cells,row):cell.text=entry
                    if index==0:
                        repeat=OxmlElement('w:tblHeader');table.rows[0]._tr.get_or_add_trPr().append(repeat)
            else:
                image_path=photo_path(block['photo']['id'])
                with PILImage.open(image_path) as image:w,h=image.size
                width=min(6.89*block['width']/100,6.5*w/h)
                host.add_paragraph().add_run().add_picture(str(image_path),width=Inches(width))
                if block['photo'].get('caption'):host.add_paragraph(block['photo']['caption'],'Caption')

    if meta.get('client'):document.add_paragraph('CLIENT: '+meta['client'])
    modules=cover_modules(project)
    cover_table=document.add_table(rows=0,cols=1)
    for index,module in enumerate(modules):
        row=cover_table.add_row();row.height=Pt([80,150,110][index] if len(modules)==3 else 340/max(1,len(modules)))
        cell=row.cells[0];heading=cell.paragraphs[0]
        borders=OxmlElement('w:pBdr');top=OxmlElement('w:top')
        for k,v in [('val','single'),('sz','4'),('color','000000')]:top.set(qn('w:'+k),v)
        borders.append(top);heading._p.get_or_add_pPr().append(borders)
        run=heading.add_run(module['title']);run.bold=True;run.font.size=Pt(9)
        write_blocks(module['blocks'],cell)
    spacer=document.add_paragraph();spacer.paragraph_format.space_after=Pt(4)
    for label,key,prefix in [('PREPARED BY','prepared_by','author'),('REVIEWED BY','reviewed_by','reviewer')]:
        p=document.add_paragraph();p.paragraph_format.tab_stops.add_tab_stop(Inches(1.1));p.add_run(label+':\t').bold=True;p.add_run(meta.get(key,'')).bold=True
        p=document.add_paragraph('\n'.join(filter(None,[meta.get(prefix+'_qualifications'),meta.get(prefix+'_title')])));p.paragraph_format.left_indent=Inches(1.1)
    table=document.add_table(rows=1,cols=6);table.style='Table Grid'
    keys=['revision','date','status','designed','checked','approved']
    for column,width in zip(table.columns,[.6,.85,2.8,.88,.88,.88]):column.width=Inches(width)
    for c,k in zip(table.rows[0].cells,keys):c.text=k.upper()
    for row in project['cal_cover']['revisions']+[{}]*max(0,4-len(project['cal_cover']['revisions'])):
        for c,k in zip(table.add_row().cells,keys):c.text=row.get(k,'')
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(0)
                for run in p.runs:run.font.size=Pt(8)
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
        write_blocks(module['blocks'])
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE')
    footer=section.footer.paragraphs[0];footer.alignment=2;footer._p.append(field)
    document.save(target)
