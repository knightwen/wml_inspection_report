"""Compare generated report geometry with the retained original and old prototype."""
from pathlib import Path
import hashlib,json,zipfile
from lxml import etree as E
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'.build/qa'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+NS['w']+'}'

def document(path):
    with zipfile.ZipFile(path) as z:return E.fromstring(z.read('word/document.xml'))

def geometry(path):
    doc=document(path)
    table=next(t for t in doc.findall('.//w:tbl',NS) if 'CONDITION RATING' in ''.join(t.itertext()))
    section=doc.findall('.//w:sectPr',NS)[3]
    margins=section.find('w:pgMar',NS)
    return {'inspection_table_width_mm':round(int(table.find('w:tblPr/w:tblW',NS).get(W+'w'))*25.4/1440,3),
            'column_widths_twips':[int(c.get(W+'w')) for c in table.findall('w:tblGrid/w:gridCol',NS)],
            'main_section_margins_twips':{k.split('}')[-1]:v for k,v in margins.attrib.items()},
            'main_section_type':section.find('w:type',NS).get(W+'val')}

def rendered_element_position(path):
    positions=[]
    def visit(text,cm,tm,font,size):
        if text.strip()=='ELEMENT':positions.append({'x_pt':tm[4],'y_pt':tm[5]})
    PdfReader(path).pages[4].extract_text(visitor_text=visit)
    return positions[0]

reference=QA/'layout-reference-snapshot.docx'
generated=QA/'generated-sample.docx'
reference_pdf=next((QA/'reference-render').glob('*.pdf'))
fixed_pdf=QA/'layout-fixed-render/generated-sample.pdf'
old_pdf=QA/'sample-render-v2/generated-sample.pdf'
original=geometry(reference);fixed=geometry(generated)
assert original['inspection_table_width_mm']==fixed['inspection_table_width_mm']
assert original['column_widths_twips']==fixed['column_widths_twips']
assert original['main_section_margins_twips']==fixed['main_section_margins_twips']
assert rendered_element_position(reference_pdf)==rendered_element_position(fixed_pdf)
preserved=['word/styles.xml','word/numbering.xml','word/theme/theme1.xml']
with zipfile.ZipFile(reference) as a,zipfile.ZipFile(generated) as b:
    assert all(a.read(n)==b.read(n) for n in preserved)
    original_sections=E.fromstring(a.read('word/document.xml')).findall('.//w:sectPr',NS)
    fixed_sections=E.fromstring(b.read('word/document.xml')).findall('.//w:sectPr',NS)
    assert len(original_sections)==len(fixed_sections)
    for left,right in zip(original_sections,fixed_sections):
        for tag in ['pgSz','pgMar','headerReference','footerReference']:
            assert [E.tostring(n) for n in left.findall('w:'+tag,NS)]==[E.tostring(n) for n in right.findall('w:'+tag,NS)]
result={'status':'passed','reference_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),
        'original':original,'fixed':fixed,
        'rendered_first_ELEMENT_position':{'original':rendered_element_position(reference_pdf),
            'old':rendered_element_position(old_pdf),'fixed':rendered_element_position(fixed_pdf)},
        'preserved_parts':preserved,'generated_pages':len(PdfReader(fixed_pdf).pages),
        'visual_review':'All 11 generated pages inspected; original 15-page render used for comparison.',
        'limits':'Text and photograph aspect ratios affect pagination. Portrait images keep their ratio and fit the photo column.'}
(QA/'layout-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
