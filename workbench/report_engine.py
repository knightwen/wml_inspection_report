"""Generate reports by cloning the retained Word template's OOXML components."""
from costs import amount, validate_rows
from inspection_items import item_subitems
from decimal import Decimal
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
import re
import zipfile
from lxml import etree as E
from PIL import Image

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS = {'w': W, 'r': R}
COLORS = {'Critical': 'FF6600', 'High': 'FF9933', 'Moderate': 'FFCC00', 'Low': '92D050', 'Urgent': 'FF0000'}
# OOXML property children are ordered sequences, even when ordinary XML parsers
# accept another order. Keep the existing formatting values while fixing order.
PROPERTY_ORDER = {
    'pPr': 'pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange',
    'rPr': 'rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange',
    'tcPr': 'cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark headers cellIns cellDel cellMerge tcPrChange',
    'settings': 'writeProtection view zoom removePersonalInformation removeDateAndTime doNotDisplayPageBoundaries displayBackgroundShape printPostScriptOverText printFractionalCharacterWidth printFormsData embedTrueTypeFonts embedSystemFonts saveSubsetFonts saveFormsData mirrorMargins alignBordersAndEdges bordersDoNotSurroundHeader bordersDoNotSurroundFooter gutterAtTop hideSpellingErrors hideGrammaticalErrors activeWritingStyle proofState formsDesign attachedTemplate linkStyles stylePaneFormatFilter stylePaneSortMethod documentType mailMerge revisionView trackRevisions doNotTrackMoves doNotTrackFormatting documentProtection autoFormatOverride styleLockTheme styleLockQFSet defaultTabStop autoHyphenation consecutiveHyphenLimit hyphenationZone doNotHyphenateCaps showEnvelope summaryLength clickAndTypeStyle defaultTableStyle evenAndOddHeaders bookFoldRevPrinting bookFoldPrinting bookFoldPrintingSheets drawingGridHorizontalSpacing drawingGridVerticalSpacing displayHorizontalDrawingGridEvery displayVerticalDrawingGridEvery doNotUseMarginsForDrawingGridOrigin drawingGridHorizontalOrigin drawingGridVerticalOrigin doNotShadeFormData noPunctuationKerning characterSpacingControl printTwoOnOne strictFirstAndLastChars noLineBreaksAfter noLineBreaksBefore savePreviewPicture doNotValidateAgainstSchema saveInvalidXml ignoreMixedContent alwaysShowPlaceholderText doNotDemarcateInvalidXml saveXmlDataOnly useXSLTWhenSaving saveThroughXslt showXMLTags alwaysMergeEmptyNamespace updateFields hdrShapeDefaults footnotePr endnotePr compat docVars rsids mathPr attachedSchema themeFontLang clrSchemeMapping doNotIncludeSubdocsInStats doNotAutoCompressPictures forceUpgrade captions readModeInkLockDown smartTagType shapeDefaults doNotEmbedSmartTags decimalSymbol listSeparator',
}

def q(name):
    return '{' + W + '}' + name

def child(parent, name, **attrs):
    node = parent.find(q(name)) if parent.tag in {q(key) for key in PROPERTY_ORDER} else None
    if node is None:node = E.SubElement(parent, q(name))
    for key, value in attrs.items():
        node.set(q(key), str(value))
    return node

def xml(node):
    return E.tostring(node, xml_declaration=True, encoding='UTF-8', standalone=True)

def paragraph(text='', style=None, bold=False):
    p = E.Element(q('p'))
    if style:
        child(child(p, 'pPr'), 'pStyle', val=style)
    r = child(p, 'r')
    if bold:
        child(child(r, 'rPr'), 'b')
    t = child(r, 't'); t.text = text; t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return p

def set_text(node, text, preserve_art=False):
    """Retain paragraph/run styling, replace the complete editable slot including fields."""
    p = node if node.tag == q('p') else node.find('w:p', NS)
    if p is None:
        p = child(node, 'p')
    oldrun = p.find('w:r', NS)
    rpr = deepcopy(oldrun.find('w:rPr', NS)) if oldrun is not None and oldrun.find('w:rPr', NS) is not None else None
    artwork=[deepcopy(n) for n in p if n.xpath('.//w:drawing | .//w:pict',namespaces=NS)] if preserve_art else []
    for n in list(p):
        if n.tag != q('pPr'):
            p.remove(n)
    for n in artwork:p.append(n)
    r = child(p, 'r')
    if rpr is not None:
        r.append(rpr)
    t = child(r, 't'); t.text = str(text); t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    if node.tag == q('tc'):
        for n in list(node):
            if n.tag not in (q('tcPr'), q('p')) or (n.tag == q('p') and n is not p):
                node.remove(n)

def page_before(p):
    pr = p.find('w:pPr', NS)
    if pr is None:
        pr = E.Element(q('pPr')); p.insert(0, pr)
    for n in pr.findall('w:pageBreakBefore', NS):
        pr.remove(n)
    child(pr, 'pageBreakBefore')

def scrub_ids(node):
    for n in node.xpath('.//w:bookmarkStart | .//w:bookmarkEnd | .//w:lastRenderedPageBreak | .//w:commentRangeStart | .//w:commentRangeEnd | .//w:commentReference', namespaces=NS):
        n.getparent().remove(n)
    for n in node.iter():
        for key in list(n.attrib):
            if key.endswith('}paraId') or key.endswith('}textId'):
                del n.attrib[key]

def prepare_template(source, target):
    with zipfile.ZipFile(source) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    doc = E.fromstring(parts['word/document.xml'])
    body = doc.find('w:body', NS)
    original = list(body)
    for index, field in [(0, 'client'), (1, 'report_number'), (2, 'cover_title'), (3, 'report_date_long')]:
        set_text(original[index], '{{' + field + '}}', preserve_art=True)
    history = original[5].findall('w:tr', NS)
    for cell, key in zip(history[2].findall('w:tc', NS), ['revision','prepared_by','reviewed_by','purpose','report_date_short']):
        set_text(cell, '{{' + key + '}}')
    for index, key in [(8,'issued_to'),(9,'project_number'),(10,'document_name')]:
        set_text(history[index].findall('w:tc', NS)[1], '{{' + key + '}}')
    authors = original[17].findall('w:tr', NS)
    for index, fields in enumerate([['prepared_by','reviewed_by'],['author_qualifications','reviewer_qualifications'],['author_title','reviewer_title']]):
        for cell, key in zip(authors[index].findall('w:tc', NS), fields):
            set_text(cell, '{{' + key + '}}')
    # Preserve the original Contents control but remove stale source entries and references.
    toc = original[21].find('w:sdtContent', NS)
    heading = deepcopy(toc.find('w:p', NS))
    for n in list(toc): toc.remove(n)
    toc.append(heading)
    p = paragraph(); p.remove(p.find('w:r', NS))
    child(child(p, 'r'), 'fldChar', fldCharType='begin')
    child(child(p, 'r'), 'instrText').text = ' TOC \\o "1-1" \\h \\z \\u '
    child(child(p, 'r'), 'fldChar', fldCharType='separate')
    toc.append(p)
    for index, label in enumerate(['INTRODUCTION','EXTERNAL BUILDING OBSERVATIONS','RECOMMENDED REMEDIAL WORKS','CONCLUSION','COST ESTIMATE'],1):
        toc.append(paragraph(f'{index}\t{label}', 'TOC1'))
    end = paragraph(); end.remove(end.find('w:r', NS))
    child(child(end, 'r'), 'fldChar', fldCharType='end'); toc.append(end)
    # An empty table cloned from the retained inspection component is the export slot.
    # The first/main inspection table is the layout authority (the source also
    # contains two narrower tables). Keep its exact grid and five header rows.
    table = deepcopy(original[34]); scrub_ids(table)
    for extra in table.findall('w:tr', NS)[6:]:table.remove(extra)
    pr = table.find('w:tblPr', NS); child(pr, 'tblCaption', val='InspectionItems')
    rows = table.findall('w:tr', NS)
    for row in rows:
        for height in row.xpath('./w:trPr/w:trHeight', namespaces=NS): height.getparent().remove(height)
    for index,row in enumerate(rows[:5]):
        cells = row.findall('w:tc', NS)
        set_text(cells[0], '')
        set_text(cells[2], '')
        if index == 2: set_text(cells[1], 'LIKELIHOOD')
        trpr = row.find('w:trPr', NS)
        if trpr is None: trpr=E.Element(q('trPr')); row.insert(0,trpr)
        child(trpr, 'tblHeader')
        # Keep all five metadata rows with the first photo.
        for p0 in row.xpath('./w:tc/w:p', namespaces=NS):
            pp = p0.find('w:pPr',NS)
            if pp is None: pp=E.Element(q('pPr')); p0.insert(0,pp)
            child(pp,'keepNext')
    for cell in rows[5].findall('w:tc', NS): set_text(cell,'')
    photo_pr=rows[5].findall('w:tc',NS)[1].find('w:tcPr',NS)
    margins=photo_pr.find('w:tcMar',NS)
    if margins is None:margins=child(photo_pr,'tcMar')
    for side in ['left','right']:
        margin=margins.find('w:'+side,NS)
        if margin is None:margin=child(margins,side)
        margin.set(q('w'),'0');margin.set(q('type'),'dxa')
    for n in table.xpath('.//w:vMerge',namespaces=NS): n.getparent().remove(n)
    # Remove inherited priority fill for the empty template.
    for n in rows[4].xpath('./w:tc[3]/w:tcPr/w:shd',namespaces=NS): n.set(q('fill'),'FFFFFF')
    cost = deepcopy(original[157]); scrub_ids(cost)
    costrows = cost.findall('w:tr', NS)
    blank = deepcopy(costrows[2])
    for c in blank.findall('w:tc',NS):
        set_text(c,'')
        for n in c.xpath('./w:tcPr/w:shd',namespaces=NS): n.set(q('fill'),'FFFFFF')
    for row in costrows[2:]: cost.remove(row)
    for _ in range(6): cost.append(deepcopy(blank))
    for n in list(body): body.remove(n)
    keep = [*original[:20], original[21], original[25], original[26], paragraph(), original[33], table,
            original[114], paragraph(), original[151], paragraph(), original[156], cost,
            original[162], original[163], original[195]]
    for h in [original[26],original[33], original[114],original[151],original[156]]: page_before(h)
    # Once chapters are empty, a continuous start inherits the preceding TOC
    # geometry in Word-compatible renderers. Start the body on its own section
    # page so the source's 17.5/15 mm margins apply, rather than the TOC's 20 mm.
    original[162].find('w:pPr/w:sectPr/w:type',NS).set(q('val'),'nextPage')
    for n in keep: body.append(n)
    scrub_ids(body)
    parts['word/document.xml'] = xml(doc)
    # Footer field display was the old source filename. Replace whole field paragraphs
    # while retaining the literal logo/banner and PAGE field.
    for name, content in list(parts.items()):
        if re.fullmatch(r'word/(header|footer)\d+\.xml', name):
            node = E.fromstring(content)
            edited=False
            for p0 in node.xpath('.//w:p',namespaces=NS):
                texts=''.join(p0.xpath('.//w:t/text()',namespaces=NS))
                instructions=''.join(p0.xpath('.//w:instrText/text()',namespaces=NS))
                if 'FILENAME' in instructions.upper() or '12477-SIR-004' in texts:
                    set_text(p0,'{{document_name}}'); edited=True
            if edited: parts[name]=xml(node)
    settings=E.fromstring(parts['word/settings.xml'])
    upd=settings.find('w:updateFields',NS)
    if upd is None: upd=child(settings,'updateFields')
    upd.set(q('val'),'true'); parts['word/settings.xml']=xml(settings)
    # Remove obsolete photo relationships and media, retaining all branding in headers.
    rels=E.fromstring(parts['word/_rels/document.xml.rels'])
    used=set(doc.xpath('//@r:embed | //@r:link | //@r:id',namespaces=NS))
    removed=[]
    for rel in list(rels):
        if rel.get('Type','').endswith('/image') and rel.get('Id') not in used:
            removed.append('word/'+rel.get('Target')); rels.remove(rel)
        if rel.get('Type','').endswith('/comments'):
            rels.remove(rel)
    parts['word/_rels/document.xml.rels']=xml(rels)
    referenced=set()
    for name, content in parts.items():
        if name.endswith('.rels'):
            for rel in E.fromstring(content):
                referenced.add(rel.get('Target','').replace('../',''))
    for name in removed:
        if name.removeprefix('word/') not in referenced: parts.pop(name,None)
    for name in list(parts):
        if name.startswith('word/comments'): parts.pop(name)
    types=E.fromstring(parts['[Content_Types].xml'])
    for n in list(types):
        if n.get('PartName','').lstrip('/') not in parts and n.tag.endswith('Override'): types.remove(n)
    parts['[Content_Types].xml']=xml(types)
    # Drop old property text (no cached previous site or named author in the portable template).
    for name in ['docProps/core.xml','docProps/custom.xml']:
        if name in parts:
            node=E.fromstring(parts[name])
            for n in list(node):node.remove(n)
            parts[name]=xml(node)
    write_package(parts,target)

def write_package(parts,target):
    parts=normalize_package(parts)
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items(): z.writestr(name,content)

def normalize_package(parts):
    """Repair property order and empty typed metadata, including older templates."""
    parts=dict(parts)
    orders={q(parent):{q(name):index for index,name in enumerate(names.split())} for parent,names in PROPERTY_ORDER.items()}
    # Mathematics properties belong to the Office Math namespace, not w:.
    settings_order=orders[q('settings')]
    settings_order['{http://schemas.openxmlformats.org/officeDocument/2006/math}mathPr']=settings_order.pop(q('mathPr'))
    for name,content in parts.items():
        if not name.endswith('.xml'):continue
        root=E.fromstring(content);changed=False
        # Reordering a parent must not change which descendants get visited.
        for parent in list(root.iter()):
            order=orders.get(parent.tag)
            if order is None:continue
            children=list(parent);ordered=sorted(children,key=lambda node:order.get(node.tag,len(order)))
            if children!=ordered:parent[:]=ordered;changed=True
        if name=='docProps/core.xml':
            for node in list(root):
                if not (node.text or '').strip():root.remove(node);changed=True
        if name=='docProps/custom.xml':
            for node in list(root):
                if not ''.join(node.itertext()).strip():root.remove(node);changed=True
        if changed:parts[name]=xml(root)
    return parts

def metadata_values(meta):
    values={key:str(value or '') for key,value in meta.items()}
    d=date.fromisoformat(values['report_date'])
    values['report_date_long']=f'{d.day} {d.strftime("%B")} {d.year}'
    values['report_date_short']=d.strftime('%d/%m/%Y')
    values['cover_title']=f'STRUCTURAL ASSET INSPECTIONS AND REMEDIAL ADVICE - {values["site"]}'
    values['document_name']=values.get('document_name') or f'{values["report_number"]}_REV{values.get("revision", "A")}-{values["client"]}-{values["site"]}'
    return values

def content_paragraph(label, text, properties=None):
    p=paragraph(); p.remove(p.find('w:r',NS))
    if properties is not None:p.insert(0,deepcopy(properties))
    else:
        pr=child(p,'pPr');child(pr,'spacing',after='0',line='240',lineRule='auto');child(pr,'jc',val='left')
    r=child(p,'r');rpr=child(r,'rPr');child(rpr,'b');child(rpr,'bCs');child(r,'t').text=label+' – '
    for index,line in enumerate(text.split('\n')):
        r=child(p,'r')
        if index: child(r,'br')
        t=child(r,'t');t.text=line;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    return p

def image_paragraph(rid, size, number, filename, width_twips):
    a='http://schemas.openxmlformats.org/drawingml/2006/main'
    wp='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    pic='http://schemas.openxmlformats.org/drawingml/2006/picture'
    w,h=size
    # Fill the retained photo column for both landscape and phone portraits.
    # Only very tall panoramas are limited to a safely printable page height.
    scale=min(width_twips/1440/w,8.0/h)
    cx,cy=int(w*scale*914400),int(h*scale*914400)
    p=paragraph();p.remove(p.find('w:r',NS))
    pp=child(p,'pPr');child(pp,'spacing',after='0',line='240',lineRule='auto');child(pp,'jc',val='left')
    drawing=child(child(p,'r'),'drawing')
    inline=E.SubElement(drawing,'{'+wp+'}inline',distT='0',distB='0',distL='0',distR='0')
    E.SubElement(inline,'{'+wp+'}extent',cx=str(cx),cy=str(cy))
    E.SubElement(inline,'{'+wp+'}docPr',id=str(number),name=filename,descr=filename)
    gf=E.SubElement(inline,'{'+wp+'}cNvGraphicFramePr'); E.SubElement(gf,'{'+a+'}graphicFrameLocks',noChangeAspect='1')
    graph=E.SubElement(inline,'{'+a+'}graphic');gd=E.SubElement(graph,'{'+a+'}graphicData',uri=pic)
    pp0=E.SubElement(gd,'{'+pic+'}pic');nv=E.SubElement(pp0,'{'+pic+'}nvPicPr')
    E.SubElement(nv,'{'+pic+'}cNvPr',id='0',name=filename);E.SubElement(nv,'{'+pic+'}cNvPicPr')
    fill=E.SubElement(pp0,'{'+pic+'}blipFill');blip=E.SubElement(fill,'{'+a+'}blip');blip.set('{'+R+'}embed',rid)
    E.SubElement(E.SubElement(fill,'{'+a+'}stretch'),'{'+a+'}fillRect')
    sp=E.SubElement(pp0,'{'+pic+'}spPr');xf=E.SubElement(sp,'{'+a+'}xfrm')
    E.SubElement(xf,'{'+a+'}off',x='0',y='0');E.SubElement(xf,'{'+a+'}ext',cx=str(cx),cy=str(cy))
    E.SubElement(E.SubElement(sp,'{'+a+'}prstGeom',prst='rect'),'{'+a+'}avLst')
    return p

def fill_report_sections(body, sections):
    """Fill direct body anchors without altering headings, tables or section geometry."""
    labels={'introduction':'introduction','remedial_works':'recommended remedial works',
            'conclusion':'conclusion','cost_estimate':'cost estimate'}
    for key,label in labels.items():
        text=sections.get(key,'')
        if not text.strip():continue
        heading=next((p for p in body.findall('w:p',NS)
                      if ''.join(p.xpath('.//w:t/text()',namespaces=NS)).strip().casefold()==label),None)
        if heading is None:raise ValueError('Word 模板缺少章节：'+label)
        following=heading.getnext()
        blank=following is not None and following.tag==q('p') and not following.xpath('.//w:t | .//w:drawing | ./w:pPr/w:sectPr',namespaces=NS)
        prototype=deepcopy(following) if blank else paragraph()
        scrub_ids(prototype)
        index=body.index(heading)+1
        if blank:body.remove(following)
        for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
            p=deepcopy(prototype);set_text(p,line)
            body.insert(index,p);index+=1

def fill_cost_table(body, rows):
    if not rows:return
    validate_rows(rows)
    table=next((t for t in body.findall('w:tbl',NS) if 'COST ESTIMATE' in ''.join(t.xpath('./w:tr[1]//w:t/text()',namespaces=NS)).upper()),None)
    if table is None:raise ValueError('Word 模板缺少费用表')
    original=table.findall('w:tr',NS);prototype=deepcopy(original[2]);scrub_ids(prototype)
    for row in original[2:]:table.remove(row)
    for row in original[:2]:
        pr=row.find('w:trPr',NS)
        if pr is None:pr=E.Element(q('trPr'));row.insert(0,pr)
        child(pr,'tblHeader')
    total=Decimal('0');complete=True
    for index,data in enumerate(rows,1):
        value=amount(data)
        if value is None:complete=False
        else:total+=value
        row=deepcopy(prototype)
        values=[str(index),data['description'],data['quantity'],data['unit'],data['rate'],format(value,',.2f') if value is not None else '',data['priority']]
        for cell,text in zip(row.findall('w:tc',NS),values):
            set_text(cell,text)
        for height in row.xpath('./w:trPr/w:trHeight',namespaces=NS):height.getparent().remove(height)
        table.append(row)
    row=deepcopy(prototype)
    for cell,text in zip(row.findall('w:tc',NS),['','TOTAL' if complete else 'SUBTOTAL (incomplete estimate)','','','',format(total,',.2f'),'']):set_text(cell,text)
    table.append(row)

def generate_report(template, project, photo_path, target):
    with zipfile.ZipFile(template) as z: parts={n:z.read(n) for n in z.namelist()}
    values=metadata_values(project['metadata'])
    for name,content in list(parts.items()):
        if name.startswith('word/') and name.endswith('.xml') and (name=='word/document.xml' or re.search(r'(header|footer)\d+\.xml$',name)):
            node=E.fromstring(content)
            for t in node.xpath('.//w:t',namespaces=NS):
                if t.text:
                    t.text=re.sub(r'\{\{(\w+)\}\}',lambda m:values.get(m[1],''),t.text)
            parts[name]=xml(node)
    doc=E.fromstring(parts['word/document.xml']);body=doc.find('w:body',NS)
    fill_report_sections(body,project.get('sections',{}))
    fill_cost_table(body,project.get('cost_rows',[]))
    slot=body.xpath('./w:tbl[w:tblPr/w:tblCaption/@w:val="InspectionItems"]',namespaces=NS)[0]
    prototype=deepcopy(slot); at=body.index(slot);body.remove(slot)
    relations=E.fromstring(parts['word/_rels/document.xml.rels'])
    used_ids={r.get('Id') for r in relations}; nextid=1000; pictureid=10000
    for itemindex,item in enumerate(project['items'],1):
        table=deepcopy(prototype);rows=table.findall('w:tr',NS);base=deepcopy(rows[5]); table.remove(rows[5])
        description_properties=base.findall('w:tc',NS)[2].find('w:p/w:pPr',NS)
        photo_width=int(base.findall('w:tc',NS)[1].find('w:tcPr/w:tcW',NS).get(q('w')))
        for ri,key in enumerate(['element','condition_rating','likelihood','severity','priority']):
            cells=rows[ri].findall('w:tc',NS);set_text(cells[2],item[key])
            if ri==0:set_text(cells[0],itemindex)
        shade=rows[4].findall('w:tc',NS)[2].find('w:tcPr/w:shd',NS)
        if shade is None: shade=child(rows[4].findall('w:tc',NS)[2].find('w:tcPr',NS),'shd')
        shade.set(q('fill'),COLORS.get(item['priority'],'FFFFFF'))
        priority_run=rows[4].findall('w:tc',NS)[2].find('w:p/w:r',NS)
        priority_rpr=priority_run.find('w:rPr',NS)
        if priority_rpr is None:priority_rpr=E.Element(q('rPr'));priority_run.insert(0,priority_rpr)
        color=priority_rpr.find('w:color',NS)
        if color is None:color=child(priority_rpr,'color')
        color.set(q('val'),'FFFFFF' if item['priority'] in ['Critical','Urgent'] else '000000')
        for attr in ['themeColor','themeTint','themeShade']:color.attrib.pop(q(attr),None)
        photo_rows=[(group,gi,photo) for group in item_subitems(item) for gi,photo in enumerate(group['photos'])]
        for pi,(group,gi,photo) in enumerate(photo_rows,1):
            row=deepcopy(base);cells=row.findall('w:tc',NS);set_text(cells[0],f'{itemindex}.{pi}')
            for cell in cells[1:]:
                for n in list(cell):
                    if n.tag!=q('tcPr'):cell.remove(n)
            description_pr=cells[2].find('w:tcPr',NS)
            for merge in description_pr.findall('w:vMerge',NS):description_pr.remove(merge)
            if len(group['photos'])>1:child(description_pr,'vMerge',val='restart' if gi==0 else 'continue')
            child(description_pr,'vAlign',val='top')
            path=photo_path(photo['id'])
            with Image.open(path) as image:size=image.size
            while 'rId'+str(nextid) in used_ids:nextid+=1
            rid='rId'+str(nextid);used_ids.add(rid);nextid+=1
            media=f'media/inspection-{itemindex}-{pi}.jpg';parts['word/'+media]=Path(path).read_bytes()
            E.SubElement(relations,'{'+P+'}Relationship',Id=rid,Type=R+'/image',Target=media)
            cells[1].append(image_paragraph(rid,size,pictureid,photo.get('caption') or photo['name'],photo_width));pictureid+=1
            if photo.get('caption','').strip():
                caption=paragraph(photo['caption']);pr=child(caption,'pPr');caption.remove(pr);caption.insert(0,pr)
                child(pr,'jc',val='center');child(pr,'spacing',before='60',after='0')
                rpr=E.Element(q('rPr'));caption.find('w:r',NS).insert(0,rpr);child(rpr,'sz',val='18')
                cells[1].append(caption)
            if gi==0:
                cells[2].append(content_paragraph('OBSERVATION',group['observation'],description_properties))
                if group['recommendation'].strip():
                    spacer=paragraph()
                    if description_properties is not None:spacer.insert(0,deepcopy(description_properties))
                    cells[2].append(spacer)
                    cells[2].append(content_paragraph('RECOMMENDATION',group['recommendation'],description_properties))
            else:
                cells[2].append(paragraph())
            # Allow exceptionally long observations to flow over pages, while normal
            # photo rows stay together. Keep headers with the first row.
            pr=row.find('w:trPr',NS)
            if pr is None:pr=E.Element(q('trPr'));row.insert(0,pr)
            for n in pr.findall('w:trHeight',NS):pr.remove(n)
            for n in pr.findall('w:cantSplit',NS):pr.remove(n)
            if len(group['observation'])+len(group['recommendation'])<2200:child(pr,'cantSplit')
            table.append(row)
        body.insert(at,table);at+=1
        gap=paragraph();body.insert(at,gap);at+=1
    parts['word/document.xml']=xml(doc);parts['word/_rels/document.xml.rels']=xml(relations)
    types=E.fromstring(parts['[Content_Types].xml'])
    if not any(n.get('Extension')=='jpg' for n in types):
        E.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Default',Extension='jpg',ContentType='image/jpeg')
    parts['[Content_Types].xml']=xml(types)
    core=E.fromstring(parts['docProps/core.xml'])
    tags={'{http://purl.org/dc/elements/1.1/}title':values['cover_title'],
          '{http://purl.org/dc/elements/1.1/}creator':values.get('prepared_by','')}
    for tag,text in tags.items():
        n=core.find(tag)
        if n is None:n=E.SubElement(core,tag)
        n.text=text
    timestamp=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    for name in ['created','modified']:
        tag='{http://purl.org/dc/terms/}'+name
        node=core.find(tag)
        if node is None:node=E.SubElement(core,tag)
        node.text=timestamp;node.set('{http://www.w3.org/2001/XMLSchema-instance}type','dcterms:W3CDTF')
    parts['docProps/core.xml']=xml(core)
    write_package(parts,target)
