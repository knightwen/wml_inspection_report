"""Offline loopback workbench. Packaged with PyInstaller; no installed runtime required."""
from datetime import datetime, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import argparse, hashlib, json, logging, mimetypes, os, re, secrets, shutil, sys, threading, time, traceback, webbrowser, zipfile
from PIL import Image, ImageOps
import pillow_heif
from lxml import etree as E
from report_engine import generate_report
from version import __version__

pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS = 100_000_000
RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'resources'
WEB=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'web'
ID=re.compile(r'^[a-f0-9]{32}$')
METADATA=['site','client','report_number','project_number','revision','report_date','prepared_by','reviewed_by','purpose','issued_to','document_name','author_qualifications','reviewer_qualifications','author_title','reviewer_title']
RATINGS=['element','condition_rating','likelihood','severity','priority']

def atomic_json(path,value):
    temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2); f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('Invalid identifier')
    return value

def read_library_xlsx(content):
    """Read only enabled wording rows. Never apply the pending review sheet."""
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    parser=E.XMLParser(resolve_entities=False,no_network=True)
    with zipfile.ZipFile(BytesIO(content)) as z:
        if sum(n.file_size for n in z.infolist())>80_000_000:raise ValueError('Excel 文件过大')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(s.itertext()) for s in E.fromstring(z.read('xl/sharedStrings.xml'),parser).findall('s:si',ns)]
        rels={n.get('Id'):n.get('Target') for n in E.fromstring(z.read('xl/_rels/workbook.xml.rels'),parser)}
        sheets=E.fromstring(z.read('xl/workbook.xml'),parser).findall('s:sheets/s:sheet',ns)
        result={}
        for name,key in [('Observation','observation'),('Recommendation','recommendation')]:
            entry=next((s for s in sheets if s.get('name')==name),None)
            if entry is None:raise ValueError(f'Excel 缺少 {name} 工作表')
            target=rels[entry.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            part=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            if '..' in part:raise ValueError('Excel 工作表路径无效')
            node=E.fromstring(z.read(part),parser);rows=[];ids=set()
            for row in node.findall('s:sheetData/s:row',ns):
                if int(row.get('r','0'))<7:continue
                values={}
                for c in row.findall('s:c',ns):
                    col=re.sub(r'\d','',c.get('r',''))
                    if c.find('s:f',ns) is not None and col in ['A','B','C','D']:
                        raise ValueError('文字库的编号、启用、描述及构件列请使用文字，不使用公式')
                    v=c.find('s:v',ns);kind=c.get('t','')
                    text=''.join(c.xpath('.//s:t/text()',namespaces=ns)) if kind=='inlineStr' else (v.text if v is not None else '')
                    if kind=='s':text=strings[int(text)]
                    values[col]=text or ''
                if values.get('B') not in ['是','Yes','yes','1']:continue
                text=values.get('C','').strip();rowid=values.get('A','').strip()
                if not text:continue
                if not rowid:rowid=f'{key.upper()}-CUSTOM-{len(rows)+1}'
                if rowid in ids:raise ValueError(f'{name} 词条编号重复：{rowid}')
                frequency=values.get('E','')
                try:frequency=int(float(frequency))
                except (ValueError,TypeError):frequency=0
                ids.add(rowid);rows.append({'id':rowid,'text':text,'elements':values.get('D',''),'frequency':frequency})
            if not rows:raise ValueError(f'{name} 没有启用的描述')
            result[key]=rows
        return result

class Store:
    def __init__(self,path):
        self.path=Path(path).resolve();self.path.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        for folder in ['projects','photos','originals','exports','backups']: (self.path/folder).mkdir(exist_ok=True)
        self.library_path=self.path/'library.json'
        if not self.library_path.exists():shutil.copyfile(RESOURCES/'library.json',self.library_path)
        self.library=json.loads(self.library_path.read_text(encoding='utf-8'))
        self.options=json.loads((RESOURCES/'options.json').read_text(encoding='utf-8'))
        self.catalog_path=self.path/'photos.json'
        self.catalog=json.loads(self.catalog_path.read_text(encoding='utf-8')) if self.catalog_path.exists() else {}

    def path_for_project(self,pid):return self.path/'projects'/(identifier(pid)+'.json')
    def load(self,pid):
        path=self.path_for_project(pid)
        if not path.exists():raise ValueError('找不到这份草稿')
        return json.loads(path.read_text(encoding='utf-8'))

    def list(self):
        result=[]
        for path in (self.path/'projects').glob('*.json'):
            p=json.loads(path.read_text(encoding='utf-8'))
            result.append({'id':p['id'],'site':p['metadata']['site'],'report_number':p['metadata']['report_number'],'updated':p['updated'],'count':len(p['items'])})
        return sorted(result,key=lambda p:p['updated'],reverse=True)

    def new(self):
        p={'id':secrets.token_hex(16),'revision':0,'updated':datetime.now().isoformat(timespec='seconds'),
           'metadata':dict.fromkeys(METADATA,''),'items':[],'editor':{'photos':[],**dict.fromkeys(RATINGS+['observation','recommendation'],'')},'editor_id':None}
        p['metadata'].update({'client':'Town of Port Hedland','revision':'A','purpose':'Information','report_date':date.today().isoformat()})
        atomic_json(self.path_for_project(p['id']),p);return p

    def validate(self,p):
        identifier(p['id'])
        if not isinstance(p.get('metadata'),dict) or not isinstance(p.get('items'),list) or len(p['items'])>1000:raise ValueError('草稿格式不正确')
        for key in METADATA:
            value=p['metadata'].get(key,'')
            if not isinstance(value,str) or len(value)>500:raise ValueError('报告信息过长')
        date.fromisoformat(p['metadata']['report_date'])
        itemids=set()
        for item in [*p['items'],p.get('editor',{})]:
            for key in RATINGS+['observation','recommendation']:
                if not isinstance(item.get(key,''),str) or len(item.get(key,''))>15000:raise ValueError('检查项文字过长')
            photos=item.get('photos',[])
            if not isinstance(photos,list) or len(photos)>100:raise ValueError('每个检查项最多 100 张照片')
            for photo in photos:
                pid=identifier(photo['id'])
                if pid not in self.catalog:raise ValueError('照片不存在，请重新导入')
                photo['name']=self.catalog[pid]['name']
            if item in p['items']:
                iid=identifier(item['id'])
                if iid in itemids:raise ValueError('检查项编号重复')
                itemids.add(iid)
                if not photos or not item.get('observation','').strip() or any(not item.get(k,'').strip() for k in RATINGS):raise ValueError('检查项缺少照片、Observation 或评级')

    def save(self,p):
        with self.lock:
            self.validate(p);path=self.path_for_project(p['id']);existing=self.load(p['id'])
            if existing['revision']!=p['revision']:raise ValueError('草稿已在其他页面更新，请刷新后重试')
            backup=self.path/'backups'/(p['id']+'.previous.json');shutil.copyfile(path,backup)
            p['revision']+=1;p['updated']=datetime.now().isoformat(timespec='seconds');atomic_json(path,p)
            return p

    def upload(self,content,name):
        name=Path(name.replace('\\','/')).name[:200];suffix=Path(name).suffix.lower()
        if suffix not in ['.jpg','.jpeg','.png','.heic','.heif','.webp']:raise ValueError('支持 JPG、PNG、WEBP、HEIC 和 HEIF')
        with Image.open(BytesIO(content)) as image:
            image.seek(0);image=ImageOps.exif_transpose(image);image.load()
            if image.width<10 or image.height<10:raise ValueError('照片尺寸太小')
            if image.mode!='RGB':
                base=Image.new('RGB',image.size,'white')
                if image.mode=='RGBA':base.paste(image,mask=image.getchannel('A'))
                else:base.paste(image.convert('RGB'))
                image=base
            image.thumbnail((2200,2200)); converted=BytesIO();image.save(converted,'JPEG',quality=88,optimize=True)
        with self.lock:
            pid=secrets.token_hex(16);(self.path/'originals'/(pid+suffix)).write_bytes(content)
            (self.path/'photos'/(pid+'.jpg')).write_bytes(converted.getvalue())
            p={'id':pid,'name':name,'original_ext':suffix,'width':image.width,'height':image.height,'sha256':hashlib.sha256(content).hexdigest()}
            self.catalog[pid]=p;atomic_json(self.catalog_path,self.catalog)
        return {'id':pid,'name':name}

    def photo_path(self,pid):return self.path/'photos'/(identifier(pid)+'.jpg')

    def rotate(self,pid):
        with self.lock:
            old=self.catalog[identifier(pid)];new=secrets.token_hex(16)
            with Image.open(self.photo_path(pid)) as image:
                image=image.rotate(-90,expand=True)
                image.save(self.photo_path(new),'JPEG',quality=92)
                ph={**old,'id':new,'width':image.width,'height':image.height}
            shutil.copyfile(self.path/'originals'/(pid+old['original_ext']),self.path/'originals'/(new+old['original_ext']))
            self.catalog[new]=ph;atomic_json(self.catalog_path,self.catalog)
            return {'id':new,'name':old['name']}

    def export(self,pid):
        with self.lock:
            p=self.load(pid);self.validate(p)
            if not p['items']:raise ValueError('请先保存至少一个检查项')
            if any(not p['metadata'].get(k,'').strip() for k in ['site','report_number','project_number']):raise ValueError('请先填写地点、报告编号和项目编号')
            eid=secrets.token_hex(16);path=self.path/'exports'/(eid+'.docx')
            generate_report(RESOURCES/'report_template.docx',p,self.photo_path,path)
            name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',p['metadata']['report_number']+'_REV'+p['metadata']['revision']+'-'+p['metadata']['site'])[:170]+'.docx'
            return {'id':eid,'name':name}

    def backup(self,pid):
        with self.lock:
            p=self.load(pid); self.validate(p)
            photoids={ph['id'] for item in [*p['items'],p['editor']] for ph in item['photos']}
            result=BytesIO()
            with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('project.json',json.dumps(p,ensure_ascii=False))
                z.writestr('photos.json',json.dumps({i:self.catalog[i] for i in photoids},ensure_ascii=False))
                for i in photoids:
                    z.write(self.photo_path(i),f'photos/{i}.jpg')
                    z.write(self.path/'originals'/(i+self.catalog[i]['original_ext']),f'originals/{i}{self.catalog[i]["original_ext"]}')
            return result.getvalue()

    def restore(self,content):
        with self.lock, zipfile.ZipFile(BytesIO(content)) as z:
            if sum(n.file_size for n in z.infolist())>2_000_000_000:raise ValueError('备份文件过大')
            p=json.loads(z.read('project.json'));photos=json.loads(z.read('photos.json'))
            mapping={identifier(i):secrets.token_hex(16) for i in photos}
            prepared=[]
            for old,new in mapping.items():
                ph=photos[old];ext=ph['original_ext']
                if ext not in ['.jpg','.jpeg','.png','.webp','.heic','.heif']:raise ValueError('备份照片格式无效')
                original=z.read(f'originals/{old}{ext}');converted=z.read(f'photos/{old}.jpg')
                with Image.open(BytesIO(converted)) as img:img.verify()
                if hashlib.sha256(original).hexdigest()!=ph['sha256']:raise ValueError('备份照片校验失败')
                prepared.append((new,{**ph,'id':new},original,converted))
            for item in [*p['items'],p['editor']]:
                for ph in item['photos']:ph['id']=mapping[ph['id']]
            p['id']=secrets.token_hex(16);p['revision']=0;p['updated']=datetime.now().isoformat(timespec='seconds')
            previous=self.catalog.copy()
            try:
                self.catalog.update({i:ph for i,ph,_,_ in prepared});self.validate(p)
                for i,ph,original,converted in prepared:
                    (self.path/'originals'/(i+ph['original_ext'])).write_bytes(original);self.photo_path(i).write_bytes(converted)
                atomic_json(self.catalog_path,self.catalog);atomic_json(self.path_for_project(p['id']),p)
            except Exception:
                self.catalog=previous;raise
            return p

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):logging.info(fmt,*args)

    def reply(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode();self.send_bytes(raw,'application/json; charset=utf-8',status)

    def send_bytes(self,content,kind,status=200,filename=None):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            from urllib.parse import quote
            self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(filename))
        self.end_headers();self.wfile.write(content)

    def authorized(self):
        host=self.headers.get('Host','')
        if host!=f'127.0.0.1:{self.server.server_port}':return False
        cookies={s.strip().split('=',1)[0]:s.strip().split('=',1)[1] for s in self.headers.get('Cookie','').split(';') if '=' in s}
        return secrets.compare_digest(cookies.get('workbench',''),self.server.token)

    def do_GET(self):
        url=urlparse(self.path);query=parse_qs(url.query)
        if url.path=='/' and query.get('key',[''])[0]==self.server.token and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}':
            self.send_response(302);self.send_header('Set-Cookie',f'workbench={self.server.token}; HttpOnly; SameSite=Strict; Path=/');self.send_header('Location','/');self.end_headers();return
        if not self.authorized():self.reply({'error':'请从程序启动的页面打开工作台'},403);return
        try:
            s=self.server.store
            if url.path=='/api/bootstrap':self.reply({'library':s.library,'options':s.options,'projects':s.list(),'data_folder':str(s.path),'version':__version__});return
            if url.path=='/api/project':self.reply(s.load(query['id'][0]));return
            if url.path.startswith('/photos/'):
                pid=url.path.split('/')[-1].removesuffix('.jpg');self.send_bytes(s.photo_path(pid).read_bytes(),'image/jpeg');return
            if url.path=='/api/download':
                eid=identifier(query['id'][0]);path=s.path/'exports'/(eid+'.docx')
                self.send_bytes(path.read_bytes(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename=query.get('name',['report.docx'])[0]);return
            if url.path=='/api/backup':self.send_bytes(s.backup(query['id'][0]),'application/zip',filename='inspection-draft.inspection.zip');return
            if url.path=='/api/library-file':
                source=s.path/'library.xlsx'
                if not source.exists():source=RESOURCES/'word_library.xlsx'
                self.send_bytes(source.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='word-library.xlsx');return
            file={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}.get(url.path)
            if not file:self.reply({'error':'Not found'},404);return
            self.send_bytes((WEB/file).read_bytes(),mimetypes.guess_type(file)[0] or 'text/plain')
        except Exception as exc:
            logging.exception('GET failure');self.reply({'error':str(exc)},400)

    def do_POST(self):
        origin=self.headers.get('Origin')
        if not self.authorized() or self.headers.get('X-Workbench')!='1' or (origin and origin!=f'http://127.0.0.1:{self.server.server_port}'):
            self.reply({'error':'Unauthorized request'},403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>1_500_000_000:raise ValueError('文件过大')
            path=urlparse(self.path).path
            limit=1_500_000_000 if path=='/api/restore' else 80_000_000 if path in ['/api/photo','/api/library'] else 5_000_000
            if length>limit:raise ValueError('文件过大')
            content=self.rfile.read(length);s=self.server.store
            if path=='/api/new':self.reply(s.new());return
            if path=='/api/photo':self.reply(s.upload(content,unquote(self.headers.get('X-Filename','photo.jpg'))));return
            if path=='/api/rotate':self.reply(s.rotate(json.loads(content)['id']));return
            if path=='/api/save':self.reply(s.save(json.loads(content)));return
            if path=='/api/generate':self.reply(s.export(json.loads(content)['id']));return
            if path=='/api/restore':self.reply(s.restore(content));return
            if path=='/api/library':
                library=read_library_xlsx(content)
                with s.lock:
                    if (s.path/'library.xlsx').exists():shutil.copyfile(s.path/'library.xlsx',s.path/'backups/library.previous.xlsx')
                    atomic_json(s.library_path,library);(s.path/'library.xlsx').write_bytes(content);s.library=library
                self.reply({'library':library});return
            if path=='/api/shutdown':
                self.reply({'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            self.reply({'error':'Not found'},404)
        except Exception as exc:
            logging.exception('POST failure');self.reply({'error':str(exc)},400)

def default_data_folder():
    base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    preferred=base/'WorkbenchData'
    try:
        preferred.mkdir(exist_ok=True);probe=preferred/'.write-test';probe.write_text('test');probe.unlink();return preferred
    except OSError:
        return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'WMLInspectionWorkbench'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir');parser.add_argument('--port',type=int,default=0);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    path=Path(args.data_dir) if args.data_dir else default_data_folder();path.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=path/'workbench.log',level=logging.INFO,encoding='utf-8',format='%(asctime)s %(levelname)s %(message)s')
    # Reuse the running app when double-clicked again. Each data folder is a single instance.
    statepath=path/'running.json'
    if statepath.exists():
        try:
            import urllib.request
            state=json.loads(statepath.read_text());port=state['port'];token=state['token']
            request=urllib.request.Request(f'http://127.0.0.1:{port}/api/bootstrap',headers={'Cookie':'workbench='+token})
            with urllib.request.urlopen(request,timeout=2) as response:
                if response.status==200:
                    if not args.no_browser:webbrowser.open(f'http://127.0.0.1:{port}/?key={token}')
                    return
        except Exception:pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.daemon_threads=True
    server.token=secrets.token_hex(32);server.store=Store(path)
    atomic_json(statepath,{'port':server.server_port,'token':server.token,'pid':os.getpid()})
    url=f'http://127.0.0.1:{server.server_port}/?key={server.token}'
    if sys.stdout:print(f'Local: {url}',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.3)
    finally:
        server.server_close()
        if statepath.exists():statepath.unlink()

if __name__=='__main__':
    try:main()
    except Exception:
        logging.exception('Startup failure')
        if getattr(sys,'frozen',False):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'工作台启动失败。请检查程序目录中的 WorkbenchData/workbench.log。','Inspection Workbench',16)
        else:raise
