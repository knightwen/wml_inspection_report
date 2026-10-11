"""Optional Windows/Word integration QA; protects pre-existing Word processes."""
from pathlib import Path
import argparse,json,sys,time,subprocess,urllib.request,urllib.parse,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'workbench'))

def word_pids():
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"@(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) | ConvertTo-Json -Compress; exit 0"],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    text=result.stdout.decode().strip();value=json.loads(text) if text else []
    return set(value if isinstance(value,list) else [value])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-data',type=Path,help='Test an already-running portable EXE in an isolated data folder.')
    parser.add_argument('--shutdown',action='store_true',help='Stop that isolated EXE after the test.')
    args=parser.parse_args()
    if args.server_data:
        folder=args.server_data.resolve()
        assert folder.is_relative_to((ROOT/'.build/qa').resolve()),'Integration testing requires an isolated QA data folder.'
        state=json.loads((folder/'running.json').read_text())
        base='http://127.0.0.1:'+str(state['port'])
        headers={'Cookie':'workbench='+state['token'],'X-Workbench':'1'}
        def request(path,body=None,extra=None):
            h={**headers,**(extra or {})}
            if isinstance(body,dict):body=json.dumps(body).encode();h['Content-Type']='application/json'
            with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=h),timeout=15) as response:return json.load(response)
        before=word_pids()
        try:
            assert request('/api/bootstrap')['preview_capability']['available']
            p=request('/api/new',{})
            photo=request('/api/photo',(ROOT/'.build/qa/upload-fixtures/landscape.jpg').read_bytes(),{'X-Filename':'native-preview.jpg'})
            p['metadata'].update(site='Native portable snapshot',report_number='QA-NATIVE-EXE',project_number='QA')
            p['items']=[{'id':'a'*32,'photos':[photo],'element':'Columns','condition_rating':'5. Major deterioration','likelihood':'Likely','severity':'Significant','priority':'Critical','observation':'Actual portable Word conversion.','recommendation':'Test recommendation.'}]
            p=request('/api/save',p);job=request('/api/preview',{'id':p['id']});started=time.monotonic()
            p['metadata']['site']='Edited while preview runs'
            saving=time.monotonic();request('/api/save',p);save_seconds=time.monotonic()-saving
            assert save_seconds<2,'Preview blocked draft saving'
            while True:
                state=request('/api/preview-job?id='+job['id'])
                if state['status'] in ['ready','failed']:break
                if time.monotonic()-started>145:raise RuntimeError('Native preview timed out')
                time.sleep(.3)
            assert state['status']=='ready',state
            report=folder/'exports'/(state['report_id']+'.docx');pdf=report.with_suffix('.pdf')
            assert pdf.read_bytes().startswith(b'%PDF-')
            with zipfile.ZipFile(report) as package:
                document=package.read('word/document.xml')
                assert b'Native portable snapshot' in document and b'Edited while preview runs' not in document
            for n in range(1,state['pages']+1):assert report.with_name(f'{report.stem}-{n}.jpg').exists()
            after=word_pids();assert before.issubset(after),'Existing Word instance was closed'
            owner=json.loads(report.with_suffix('.word-owner.json').read_text(encoding='utf-8-sig'))
            assert owner['pid'] not in after,'Owned Word process was not cleaned up'
            result={'status':'passed','mode':'portable EXE with actual Word and PDFium','pages':state['pages'],'existing_word_processes_preserved':len(before),'owned_word_process_closed':True,'snapshot_preserved':True,'save_seconds_during_preview':round(save_seconds,3),'report':str(report),'pdf':str(pdf)}
            (ROOT/'.build/qa/native-frozen-preview-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
        finally:
            if args.shutdown:request('/api/shutdown',{})
        raise SystemExit(0)
    from app import Store
    from preview import word_capability
    capability=word_capability()
    if not capability['available']:raise SystemExit('Native Word integration requires an installed Word; run no-Word tests separately.')
    before=word_pids();folder=ROOT/'.build/qa/native-preview-data';store=Store(folder)
    try:
        p=store.new();photo=store.upload((ROOT/'.build/qa/upload-fixtures/landscape.jpg').read_bytes(),'native-preview.jpg')
        p['metadata'].update(site='Native Word Preview QA',report_number='QA-NATIVE',project_number='QA')
        p['items']=[{'id':'a'*32,'photos':[photo],'element':'Columns','condition_rating':'5. Major deterioration','likelihood':'Likely','severity':'Significant','priority':'Critical','observation':'Native preview test.','recommendation':'Test recommendation.'}]
        p=store.save(p);job=store.preview(p['id']);started=time.monotonic()
        while True:
            state=store.previews.get(job['id'])
            if state['status'] in ['ready','failed']:break
            if time.monotonic()-started>145:raise RuntimeError('Preview job exceeded its timeout')
            time.sleep(.3)
        assert before.issubset(word_pids()),'A pre-existing Word process was unexpectedly closed'
        assert state['status']=='ready',state
        report=folder/'exports'/(state['report_id']+'.docx');pdf=report.with_suffix('.pdf')
        assert pdf.read_bytes().startswith(b'%PDF-')
        for n in range(1,state['pages']+1):assert report.with_name(f'{report.stem}-{n}.jpg').exists()
        result={'status':'passed','pages':state['pages'],'existing_word_processes_preserved':len(before),'report':str(report),'pdf':str(pdf)}
        (ROOT/'.build/qa/native-preview-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:store.previews.close()
