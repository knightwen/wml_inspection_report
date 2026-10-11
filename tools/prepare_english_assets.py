"""Build English-only UI and default resources without modifying source presets."""
import json, shutil, zipfile
from pathlib import Path
from lxml import etree, html
from distribution import ROOT

def prepare_english_assets(target):
    target=Path(target)
    for directory in ['web','resources']:shutil.copytree(ROOT/'workbench'/directory,target/directory)
    web=target/'web';resources=target/'resources'
    text=(web/'translations-en.js').read_text(encoding='utf-8')
    translations=json.loads(text.split('window.WorkbenchEnglish = ',1)[1].strip().removesuffix(';'))
    page=html.fromstring((web/'index.html').read_text(encoding='utf-8'))
    page.set('lang','en-AU')
    for el in page.iter():
        key=el.get('data-i18n')
        if key:el.text=translations[key]
        key=el.get('data-i18n-tail')
        if key:el.tail=translations[key]
        for attr in ['placeholder','title','aria-label']:
            key=el.get('data-i18n-'+attr)
            if key:el.set(attr,translations[key])
        for attr in list(el.attrib):
            if attr.startswith('data-i18n'):del el.attrib[attr]
    switch=page.get_element_by_id('languageSelect');switch.getparent().remove(switch)
    (web/'index.html').write_text('<!doctype html>\n'+html.tostring(page,encoding='unicode')+'\n',encoding='utf-8')
    (web/'interface.js').write_text("'use strict';\nwindow.WorkbenchInterface = {englishOnly: true};\n",encoding='utf-8')
    (resources/'ui_config.json').write_text('{"edition":"english"}\n',encoding='utf-8')
    personnel=json.loads((resources/'personnel.json').read_text(encoding='utf-8'))
    for person,name in zip(personnel['people'],['Example author (please edit)','Example reviewer (please edit)']):person['name']=name
    (resources/'personnel.json').write_text(json.dumps(personnel,indent=2)+'\n',encoding='utf-8')
    replacements={
        '常用描述（可编辑）':'Common wording (editable)',
        '常见构件（可编辑）':'Common elements (editable)',
        '黄色列可编辑；新增从第 7 行起填写 A–D 列，编号须唯一。':'Edit the yellow columns. Add entries from row 7 in columns A-D, using unique IDs.',
        '筛选标准：历史报告出现至少 2 次。保留原词条编号。':'Selection: used at least twice in historical reports. Original entry IDs are retained.',
        'Observation 常用措辞':'Observation common wording',
        'Recommendation 常用措辞':'Recommendation common wording',
        '词条编号':'Entry ID','历史次数':'Historical frequency',
        '；启用 ':'; enabled ','词条 ':'Entries ',
        '启用':'Enabled','是':'Yes','否':'No',
    }
    def translate(value):
        if value:
            for source,english in replacements.items():value=value.replace(source,english)
        return value
    workbook=resources/'word_library.xlsx'
    with zipfile.ZipFile(workbook) as z:parts={name:z.read(name) for name in z.namelist()}
    for name,content in parts.items():
        if not name.endswith('.xml'):continue
        node=etree.fromstring(content)
        for el in node.iter():
            if el.text:el.text=translate(el.text)
            for attr,value in el.attrib.items():el.set(attr,translate(value))
        parts[name]=etree.tostring(node,xml_declaration=True,encoding='UTF-8',standalone=True)
    with zipfile.ZipFile(workbook,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in parts.items():z.writestr(name,content)
    return web,resources
