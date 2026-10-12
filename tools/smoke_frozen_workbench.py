"""Unzip and launch the actual portable EXE, then test its loopback API."""
import argparse
from io import BytesIO
import json
import os
import secrets
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from PIL import Image
import pillow_heif
from distribution import ROOT as root, VERSION, edition_paths


def exercise(executable, folder, fixtures, qa, edition):
    statepath = folder / 'running.json'
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if statepath.is_file():
            state = json.loads(statepath.read_text(encoding='utf-8'))
            break
        time.sleep(0.2)
    else:
        log = folder / 'workbench.log'
        raise RuntimeError('EXE startup timed out. ' + (log.read_text(encoding='utf-8') if log.exists() else 'No log created.'))
    base = f'http://127.0.0.1:{state["port"]}'
    headers = {'Cookie': 'workbench=' + state['token'], 'X-Workbench': '1'}

    def request(path, body=None, extra=None, raw=False):
        h = {**headers, **(extra or {})}
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        with urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=h), timeout=30) as response:
            data = response.read()
            return data if raw else json.loads(data)

    boot=request('/api/bootstrap');assert len(boot['library']['observation'])==90 and len(boot['library']['recommendation'])==44
    assert boot['version']==VERSION
    assert boot['edition']==edition
    assert Path(boot['data_folder']) == folder
    page=request('/',raw=True).decode()
    assert '<!doctype html' in page.lower()
    if edition=='english':
        import re
        assert 'languageSelect' not in page and not re.search(r'[\u4e00-\u9fff]',page)
        assert 'englishOnly: true' in request('/interface.js',raw=True).decode()
    else:assert 'languageSelect' in page
    for asset in ('/app.js','/style.css','/favicon.svg','/interface.js','/i18n.js','/translations-en.js'):
        assert request(asset,raw=True)
    personnel=request('/api/personnel');assert len(personnel['people'])==2
    personnel['people'][0].update(name='Frozen Test Author',qualifications='Test Qualification',title='Test Author Title',roles=['author','reviewer'])
    personnel=request('/api/personnel',personnel)
    assert request('/api/personnel')==personnel
    p=request('/api/new',{})
    p['metadata'].update(site='Frozen EXE Test',project_number='TEST',report_number='TEST-SIR-EXE',prepared_by='Test Author',reviewed_by='Test Reviewer')
    person=personnel['people'][0]
    p['metadata'].update(prepared_by=person['name'],prepared_by_id=person['id'],author_qualifications=person['qualifications'],author_title=person['title'])
    photos=[]
    for name in ['landscape.jpg','portrait.heic']:
        fixture=fixtures/name
        photo=request('/api/photo',fixture.read_bytes(),{'X-Filename':urllib.parse.quote(name)})
        original=folder/'originals'/(photo['id']+fixture.suffix)
        assert original.read_bytes()==fixture.read_bytes();photos.append(photo)
    rotated=request('/api/rotate',{'id':photos[0]['id']});assert rotated['id']!=photos[0]['id']
    photos[0]=rotated
    edited=request('/api/photo-edit',{'id':rotated['id'],'operations':[{'type':'crop','box':[20,30,520,630]},{'type':'circle','box':[30,30,200,200]},{'type':'arrow','box':[250,400,400,450],'color':'#1677ff','width':8}]})
    photos[0]={**edited,'caption':'Edited portable photograph'}
    assert (folder/'originals'/(edited['id']+'.jpg')).read_bytes()==(fixtures/'landscape.jpg').read_bytes()
    with Image.open(BytesIO(request('/photos/'+edited['id']+'.jpg',raw=True))) as image:assert image.size==(500,600)
    item={'id':'a'*32,'photos':photos,'element':'Columns','condition_rating':'5. Major deterioration','likelihood':'Likely','severity':'Significant','priority':'Critical','observation':'Minor corrosion. Manually edited in the standalone EXE test.','recommendation':'Clean, wire brush and repaint.'}
    p['items']=[item];p=request('/api/save',p)
    # Older flat items migrate before adding independently described photo groups.
    migrated=p['items'][0]['subitems'][0]
    assert migrated['observation']==item['observation'] and len(migrated['photos'])==2
    migrated['photos']=photos[:1]
    p['items'][0]['subitems'] += [
        {'id':secrets.token_hex(16),'photos':photos[::-1],
         'observation':'Independent second subitem with two photographs.','recommendation':''},
        {'id':secrets.token_hex(16),'photos':photos[1:],
         'observation':'Independent third subitem.','recommendation':'Review the third group only.'},
    ]
    p=request('/api/save',p)
    assert [len(g['photos']) for g in p['items'][0]['subitems']]==[1,2,1]
    export=request('/api/generate',{'id':p['id']})
    report=request('/api/download?id='+export['id'],raw=True)
    with zipfile.ZipFile(BytesIO(report)) as z:
        document=z.read('word/document.xml').decode()
        assert 'Frozen EXE Test' in document and item['observation'] in document
        assert all(value in document for value in ['Frozen Test Author','Test Qualification','Test Author Title'])
        assert 'Edited portable photograph' in document
        assert z.read('word/media/inspection-1-1.jpg')==(folder/'photos'/(edited['id']+'.jpg')).read_bytes()
        assert '{{' not in document and '1/19 Dempster' not in document
        assert len([n for n in z.namelist() if n.startswith('word/media/inspection-')])==4
        from lxml import etree
        tree=etree.fromstring(z.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
        tables=[t for t in tree.findall('.//w:tbl',ns) if 'CONDITION RATING' in ''.join(t.itertext())]
        assert tables and all(t.find('w:tblPr/w:tblW',ns).get('{'+ns['w']+'}w')=='9771' for t in tables)
        assert [c.get('{'+ns['w']+'}w') for c in tables[0].findall('w:tblGrid/w:gridCol',ns)]==['703','3259','5809']
        rows=tables[0].findall('w:tr',ns)[5:]
        assert [''.join(r.find('w:tc',ns).itertext()) for r in rows]==['1.1','1.2','1.3','1.4']
        merges=[r.findall('w:tc',ns)[2].find('w:tcPr/w:vMerge',ns) for r in rows]
        assert [m.get('{'+ns['w']+'}val') if m is not None else None for m in merges]==[None,'restart','continue',None]
        for group in p['items'][0]['subitems']:assert document.count(group['observation'])==1
        assert document.count('Review the third group only.')==1
        assert all(abs(int(e.get('cx'))-3259*635)<=1 for t in tables for e in t.findall('.//wp:extent',ns))
        with zipfile.ZipFile(root/'workbench/resources/report_template.docx') as template:
            assert z.read('word/styles.xml')==template.read('word/styles.xml')
    (qa/'frozen-generated.docx').write_bytes(report)
    backup=request('/api/backup?id='+p['id'],raw=True)
    restored=request('/api/restore',backup);assert restored['id']!=p['id'] and restored['items'][0]['subitems'][0]['observation']==item['observation']
    assert restored['items'][0]['subitems'][0]['photos'][0]['id']!=photos[0]['id']
    assert [len(g['photos']) for g in restored['items'][0]['subitems']]==[1,2,1]
    assert [g['observation'] for g in restored['items'][0]['subitems']]==[g['observation'] for g in p['items'][0]['subitems']]
    library=request('/api/library',(root/'workbench/resources/word_library.xlsx').read_bytes())['library']
    assert len(library['observation'])==90 and len(library['recommendation'])==44
    assert request('/api/project?id='+p['id'])['items'][0]['subitems'][0]['observation']==item['observation']
    before=len(request('/api/bootstrap')['projects'])
    for path,data,h in [('/api/bootstrap',None,{'Cookie':''}),('/api/new',b'', {'Origin':'https://example.invalid'}),('/api/new',b'', {'X-Workbench':''})]:
        try:request(path,data,h);raise AssertionError('Expected rejection')
        except urllib.error.HTTPError as e:assert e.code==403
    assert len(request('/api/bootstrap')['projects'])==before

    stale=json.loads(json.dumps(p));p['metadata']['site']='Remote update';p=request('/api/save',p)
    stale['metadata']['site']='Local unsaved update'
    try:request('/api/save',stale);raise AssertionError('Expected conflict')
    except urllib.error.HTTPError as error:
        assert error.code==409 and json.loads(error.read())['code']=='revision_conflict'
    copy=request('/api/project-copy',stale);assert copy['id']!=p['id'] and copy['metadata']['site']=='Local unsaved update'
    recovery=request('/api/recovery-backup',stale,raw=True);assert request('/api/restore',recovery)['metadata']['site']=='Local unsaved update'
    p['metadata'].update(prepared_by='Manual portable author',prepared_by_id='');p=request('/api/save',p)
    assert p['metadata']['author_qualifications']=='' and p['metadata']['author_title']==''
    assert boot['preview_capability']['available'] is False
    try:request('/api/preview',{'id':p['id']});raise AssertionError('No Word preview should fail clearly')
    except urllib.error.HTTPError as error:assert error.code==400 and 'Word' in json.loads(error.read())['error']
    assert request('/api/generate',{'id':p['id']})['id']
    repeated=subprocess.run([str(executable),'--no-browser'],capture_output=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    assert repeated.returncode==0 and request('/api/bootstrap')['version']==VERSION

    request('/api/shutdown', {})
    return {'status': 'passed', 'version': VERSION, 'edition':edition, 'report_bytes': len(report),
            'checks': ['ZIP extraction', 'standalone startup and web assets', 'portable data folder',
                       'HEIC/JPG import', 'rotation/crop/annotation and originals', 'save/reopen', 'DOCX export',
                       'legacy item migration', 'subitems with shared ratings and independent wording', 'continuous photo numbering and description cell merging',
                       'all-subitem backup/restore', 'Excel library', 'personnel snapshot and manual clearing', 'loopback authentication', 'conflict/copy/recovery ZIP', 'no Word environment with DOCX export', 'repeated startup', 'shutdown']}


def verify_readonly_fallback(executable,directory,environment,edition):
    restricted=directory/'readonly-program';restricted.mkdir()
    test_exe=restricted/executable.name;shutil.copyfile(executable,test_exe)
    assert restricted.resolve().is_relative_to((root/'.build/qa').resolve())
    profile=directory/'fallback-profile';profile.mkdir()
    test_env={**environment,'LOCALAPPDATA':str(profile)}
    acl=subprocess.run(['icacls',str(restricted),'/deny','*S-1-1-0:(W)'],capture_output=True)
    if acl.returncode:raise RuntimeError('Unable to set isolated read-only test directory: '+repr(acl.stderr))
    process=None
    try:
        try:(restricted/'.write-probe').write_text('test');raise AssertionError('Read-only test did not block writes')
        except PermissionError:pass
        process=subprocess.Popen([str(test_exe),'--no-browser'],cwd=directory,env=test_env,creationflags=subprocess.CREATE_NO_WINDOW)
        folder=profile/('WMLInspectionWorkbenchEnglish' if edition=='english' else 'WMLInspectionWorkbench');deadline=time.monotonic()+60
        while not (folder/'running.json').exists():
            if time.monotonic()>deadline:raise RuntimeError('Read-only fallback did not start')
            time.sleep(.2)
        state=json.loads((folder/'running.json').read_text());base='http://127.0.0.1:'+str(state['port']);headers={'Cookie':'workbench='+state['token'],'X-Workbench':'1'}
        with urllib.request.urlopen(urllib.request.Request(base+'/api/bootstrap',headers=headers)) as response:boot=json.load(response)
        assert Path(boot['data_folder'])==folder and boot['version']==VERSION
        with urllib.request.urlopen(urllib.request.Request(base+'/api/shutdown',data=b'{}',headers={**headers,'Content-Type':'application/json'})) as response:assert json.load(response)['ok']
        assert process.wait(timeout=15)==0
    finally:
        if process and process.poll() is None:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True);process.wait(timeout=15)
        # Restore permissions only on this verified, task-created directory.
        restored=subprocess.run(['icacls',str(restricted),'/remove:d','*S-1-1-0'],capture_output=True)
        if restored.returncode:raise RuntimeError('Unable to restore isolated test directory permissions')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--edition',choices=['bilingual','english'],default='bilingual')
    args = parser.parse_args()
    name,_,default_archive=edition_paths(args.edition)
    args.zip=args.zip or default_archive
    qa = root / '.build/qa'
    if args.edition=='english':qa=qa/'english'
    qa.mkdir(parents=True, exist_ok=True)
    # Test a fresh, Unicode directory with spaces, using the EXE's default data location.
    with tempfile.TemporaryDirectory(prefix='portable 验证 ', dir=qa) as temporary:
        directory = Path(temporary).resolve()
        with zipfile.ZipFile(args.zip) as archive:
            for entry in archive.namelist():
                if not (directory / entry).resolve().is_relative_to(directory):
                    raise RuntimeError('Archive contains an unsafe path')
            assert archive.testzip() is None
            assert name+('/README.txt' if args.edition=='english' else '/使用说明.txt') in archive.namelist()
            assert name+'/source/tools/heic_sources.json' in archive.namelist()
            assert any(entry.startswith(name+'/LICENSES/') for entry in archive.namelist())
            assert not any('WorkbenchData' in entry or '__pycache__' in entry for entry in archive.namelist())
            archive.extractall(directory)
        executable = directory / name / (name+'.exe')
        folder=executable.parent/('WorkbenchDataEnglish' if args.edition=='english' else 'WorkbenchData')
        fixtures = directory / 'fixtures'
        fixtures.mkdir()
        pillow_heif.register_heif_opener()
        Image.new('RGB', (800, 600), '#789977').save(fixtures / 'landscape.jpg')
        Image.new('RGB', (320, 480), '#789977').save(fixtures / 'portrait.heic', 'HEIF')
        environment = {k:v for k,v in os.environ.items() if not k.startswith('PYTHON')}
        environment['PATH'] = os.environ.get('SystemRoot', r'C:\Windows') + r'\System32'
        environment['WML_DISABLE_WORD_PREVIEW']='1'  # Deterministic no-Word scenario; registry capability is also tested separately.
        process = subprocess.Popen([str(executable), '--no-browser'], cwd=directory, env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            result = exercise(executable, folder, fixtures, qa, args.edition)
            assert process.wait(timeout=15) == 0
        except Exception:
            log = folder/'workbench.log'
            if log.exists():
                shutil.copyfile(log, qa / 'frozen-failure.log')
            raise
        finally:
            if process.poll() is None:
                # PyInstaller onefile uses a child process; clean up the entire test tree.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=15)
        verify_readonly_fallback(executable,directory,environment,args.edition)
        result['checks'].append('real read-only program directory fallback')
        (qa / 'frozen-smoke-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))


if __name__ == '__main__':
    main()
