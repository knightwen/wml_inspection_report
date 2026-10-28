"""Isolated browser QA server: real app, controlled Word converter, real PDF renderer."""
from pathlib import Path
import argparse,json,sys,threading,time,secrets,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'workbench'))
import app
from preview import PreviewManager

def fixture_pdf():
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << >> /Contents 4 0 R >>',b'<< /Length 0 >>\nstream\n\nendstream']
    content=b'%PDF-1.4\n';offsets=[0]
    for number,value in enumerate(objects,1):offsets.append(len(content));content+=str(number).encode()+b' 0 obj\n'+value+b'\nendobj\n'
    start=len(content);content+=b'xref\n0 5\n0000000000 65535 f \n'
    for offset in offsets[1:]:content+=f'{offset:010d} 00000 n \n'.encode()
    return content+f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()

def fake_converter(source,resources,cancel):
    for _ in range(40):
        if cancel.is_set():raise ValueError('QA preview cancelled')
        time.sleep(.1)
    with zipfile.ZipFile(source) as package:
        part='xl/worksheets/sheet3.xml' if source.suffix=='.xlsx' else 'word/document.xml'
        if b'QA FAIL PREVIEW' in package.read(part):raise ValueError('QA conversion failure: please retry')
    pdf=source.with_suffix('.pdf');pdf.write_bytes(fixture_pdf());return pdf

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',required=True);args=parser.parse_args()
    store=app.Store(args.data_dir);store.previews=PreviewManager(store,app.RESOURCES,converter=fake_converter,capability=lambda:{'available':True},excel_converter=fake_converter,excel_check=lambda:{'available':True})
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);server.daemon_threads=True;server.store=store;server.token=secrets.token_hex(32)
    print(json.dumps({'port':server.server_port,'token':server.token}),flush=True)
    try:server.serve_forever(poll_interval=.2)
    finally:store.previews.close();server.server_close()
