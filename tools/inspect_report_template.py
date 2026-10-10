import json, zipfile, hashlib
from pathlib import Path
from lxml import etree as E
root=Path(__file__).resolve().parents[1]
source=root/'reference_reports/REVA/1_19_Dempster_Street/12477-SIR-004_REVA-Town of Port Hedland-1 19 Dempster Street.docx'
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
out=root/'.build/qa';out.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(source) as z:
    doc=E.fromstring(z.read('word/document.xml'))
    body=doc.find('w:body',ns)
    children=[]
    for i,node in enumerate(body):
        entry={'index':i,'tag':E.QName(node).localname,'text':'|'.join(node.xpath('.//w:t/text()',namespaces=ns))[:2500]}
        if entry['tag']=='p':
            entry['style']=node.xpath('./w:pPr/w:pStyle/@w:val',namespaces=ns)
            entry['section']=bool(node.xpath('./w:pPr/w:sectPr',namespaces=ns))
            entry['page_breaks']=node.xpath('.//w:br/@w:type',namespaces=ns)
        if entry['tag']=='tbl':
            entry['rows']=[['|'.join(c.xpath('.//w:t/text()',namespaces=ns))[:1000] for c in r.findall('w:tc',ns)] for r in node.findall('w:tr',ns)]
        children.append(entry)
    inventory=[{'path':n,'size':len(z.read(n)),'sha256':hashlib.sha256(z.read(n)).hexdigest()} for n in z.namelist()]
    sections=[E.tostring(s).decode() for s in doc.xpath('.//w:sectPr',namespaces=ns)]
    info={'reference':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'children':children,'sections':sections,'parts':inventory,
          'fields':doc.xpath('.//w:instrText/text()',namespaces=ns)}
    (out/'template_inventory.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'template_document.xml').write_bytes(E.tostring(doc,pretty_print=True))
    print(json.dumps({'children':children,'sections':sections,'fields':info['fields']},ensure_ascii=True,indent=2))
