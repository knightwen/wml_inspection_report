"""Unzip and launch the actual portable EXE, then test its loopback API."""
import argparse
from io import BytesIO
import json
import os
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
from distribution import ARCHIVE, ROOT as root, VERSION


def exercise(executable, folder, fixtures, qa):
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

    boot=request('/api/bootstrap');assert len(boot['library']['observation'])==622 and len(boot['library']['recommendation'])==175
    assert boot['version']==VERSION
    assert Path(boot['data_folder']) == folder
    assert b'<!doctype html' in request('/',raw=True).lower()
    for asset in ('/app.js','/style.css','/favicon.svg'):
        assert request(asset,raw=True)
    p=request('/api/new',{})
    p['metadata'].update(site='Frozen EXE Test',project_number='TEST',report_number='TEST-SIR-EXE',prepared_by='Test Author',reviewed_by='Test Reviewer')
    photos=[]
    for name in ['landscape.jpg','portrait.heic']:
        fixture=fixtures/name
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
    (qa/'frozen-generated.docx').write_bytes(report)
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

    request('/api/shutdown', {})
    return {'status': 'passed', 'version': VERSION, 'report_bytes': len(report),
            'checks': ['ZIP extraction', 'standalone startup and web assets', 'portable data folder',
                       'HEIC/JPG import', 'rotation and originals', 'save/reopen', 'DOCX export',
                       'backup/restore', 'Excel library', 'loopback authentication', 'shutdown']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, default=ARCHIVE)
    args = parser.parse_args()
    qa = root / '.build/qa'
    qa.mkdir(parents=True, exist_ok=True)
    # Test a fresh, Unicode directory with spaces, using the EXE's default data location.
    with tempfile.TemporaryDirectory(prefix='portable 验证 ', dir=qa) as temporary:
        directory = Path(temporary).resolve()
        with zipfile.ZipFile(args.zip) as archive:
            for name in archive.namelist():
                if not (directory / name).resolve().is_relative_to(directory):
                    raise RuntimeError('Archive contains an unsafe path')
            assert archive.testzip() is None
            assert 'InspectionWorkbench/使用说明.txt' in archive.namelist()
            assert 'InspectionWorkbench/source/tools/heic_sources.json' in archive.namelist()
            assert any(name.startswith('InspectionWorkbench/LICENSES/') for name in archive.namelist())
            assert not any('WorkbenchData' in name or '__pycache__' in name for name in archive.namelist())
            archive.extractall(directory)
        executable = directory / 'InspectionWorkbench/InspectionWorkbench.exe'
        fixtures = directory / 'fixtures'
        fixtures.mkdir()
        pillow_heif.register_heif_opener()
        Image.new('RGB', (800, 600), '#789977').save(fixtures / 'landscape.jpg')
        Image.new('RGB', (320, 480), '#789977').save(fixtures / 'portrait.heic', 'HEIF')
        environment = {k:v for k,v in os.environ.items() if not k.startswith('PYTHON')}
        environment['PATH'] = os.environ.get('SystemRoot', r'C:\Windows') + r'\System32'
        process = subprocess.Popen([str(executable), '--no-browser'], cwd=directory, env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            result = exercise(executable, executable.parent / 'WorkbenchData', fixtures, qa)
            assert process.wait(timeout=15) == 0
        except Exception:
            log = executable.parent / 'WorkbenchData/workbench.log'
            if log.exists():
                shutil.copyfile(log, qa / 'frozen-failure.log')
            raise
        finally:
            if process.poll() is None:
                # PyInstaller onefile uses a child process; clean up the entire test tree.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=15)
        (qa / 'frozen-smoke-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))


if __name__ == '__main__':
    main()
