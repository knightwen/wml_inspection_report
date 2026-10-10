"""Exercise the shipped executable's HTTP API; no application modules are imported."""
from pathlib import Path
from io import BytesIO
import json,sys,urllib.request,urllib.error,urllib.parse,zipfile,hashlib

root=Path(__file__).resolve().parents[1]
folder=root/'.build/qa/frozen-v011-data'
state=json.loads((folder/'running.json').read_text())
base=f'http://127.0.0.1:{state["port"]}'
headers={'Cookie':'workbench='+state['token'],'X-Workbench':'1'}
def request(path,body=None,extra=None,raw=False):
    h={**headers,**(extra or {})}
    if isinstance(body,dict):body=json.dumps(body).encode();h['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=h),timeout=30) as response:
        data=response.read()
        return data if raw else json.loads(data)
boot=request('/api/bootstrap');assert len(boot['library']['observation'])==622 and len(boot['library']['recommendation'])==175
assert boot['version']=='0.1.1'
p=request('/api/new',{})
p['metadata'].update(site='Frozen EXE Test',project_number='TEST',report_number='TEST-SIR-EXE',prepared_by='Test Author',reviewed_by='Test Reviewer')
photos=[]
for name in ['landscape.jpg','portrait.heic']:
    fixture=root/'.build/qa/upload-fixtures'/name
    photo=request('/api/photo',fixture.read_bytes(),{'X-Filename':urllib.parse.quote(name)})
    original=folder/'originals'/(photo['id']+fixture.suffix)
    assert original.read_bytes()==fixture.read_bytes();photos.append(photo)
rotated=request('/api/rotate',{'id':photos[0]['id']});assert rotated['id']!=photos[0]['id']
photos[0]=rotated
item={'id':'a'*32,'photos':photos,'element':'Columns','condition_rating':'5. Major deterioration','likelihood':'Likely','severity':'Significant','priority':'Critical','observation':'Minor corrosion. Manually edited in the standalone EXE test.','recommendation':'Clean, wire brush and repaint.'}
p['items']=[item];p=request('/api/save',p)
export=request('/api/generate',{'id':p['id']})
report=request('/api/download?id='+export['id'],raw=True)
with zipfile.ZipFile(BytesIO(report)) as z:
    document=z.read('word/document.xml').decode()
    assert 'Frozen EXE Test' in document and item['observation'] in document
    assert '{{' not in document and '1/19 Dempster' not in document
    assert len([n for n in z.namelist() if n.startswith('word/media/inspection-')])==2
    from lxml import etree
    tree=etree.fromstring(z.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
    tables=[t for t in tree.findall('.//w:tbl',ns) if 'CONDITION RATING' in ''.join(t.itertext())]
    assert tables and all(t.find('w:tblPr/w:tblW',ns).get('{'+ns['w']+'}w')=='9771' for t in tables)
    assert [c.get('{'+ns['w']+'}w') for c in tables[0].findall('w:tblGrid/w:gridCol',ns)]==['703','3259','5809']
    assert all(abs(int(e.get('cx'))-3259*635)<=1 for t in tables for e in t.findall('.//wp:extent',ns))
    with zipfile.ZipFile(root/'workbench/resources/report_template.docx') as template:
        assert z.read('word/styles.xml')==template.read('word/styles.xml')
(root/'.build/qa/frozen-v011-generated.docx').write_bytes(report)
backup=request('/api/backup?id='+p['id'],raw=True)
restored=request('/api/restore',backup);assert restored['id']!=p['id'] and restored['items'][0]['observation']==item['observation']
assert restored['items'][0]['photos'][0]['id']!=photos[0]['id']
library=request('/api/library',(root/'workbench/resources/word_library.xlsx').read_bytes())['library']
assert len(library['observation'])==622 and len(library['recommendation'])==175
assert request('/api/project?id='+p['id'])['items'][0]['observation']==item['observation']
before=len(request('/api/bootstrap')['projects'])
for path,data,h in [('/api/bootstrap',None,{'Cookie':''}),('/api/new',b'', {'Origin':'https://example.invalid'}),('/api/new',b'', {'X-Workbench':''})]:
    try:request(path,data,h);raise AssertionError('Expected rejection')
    except urllib.error.HTTPError as e:assert e.code==403
assert len(request('/api/bootstrap')['projects'])==before
result={'status':'passed','executable':str(root/'outputs/workbench_v0.1.1/InspectionWorkbench.exe'),'counts':{'observation':622,'recommendation':175},'checks':['standalone startup','HEIC/JPG import','rotation/original preservation','save and reopen','DOCX template export','backup and restore','Excel library import','loopback authentication'],'report_bytes':len(report),'project_id':p['id']}
(root/'.build/qa/frozen-v011-smoke-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
