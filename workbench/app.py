"""Offline loopback workbench. Packaged with PyInstaller; no installed runtime required."""
from datetime import datetime, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import argparse, hashlib, json, logging, mimetypes, os, re, secrets, shutil, subprocess, sys, threading, time, traceback, webbrowser, zipfile
from PIL import Image, ImageOps
import pillow_heif
from lxml import etree as E
from report_engine import generate_report
from version import __version__
from preview import PreviewManager,word_capability
from ratings import DEFAULT_RATING_OPTIONS
from inspection_items import blank_item, normalize_project, all_photos

pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS = 100_000_000
RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'resources'
WEB=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'web'
UI_CONFIG=json.loads((RESOURCES/'ui_config.json').read_text(encoding='utf-8'))
LIBRARY_POLICY=json.loads((RESOURCES/'library_policy.json').read_text(encoding='utf-8'))
ID=re.compile(r'^[a-f0-9]{32}$')
METADATA=['site','client','report_number','project_number','revision','report_date','prepared_by','reviewed_by','purpose','issued_to','document_name','author_qualifications','reviewer_qualifications','author_title','reviewer_title']
from costs import validate_rows
SECTION_FIELDS=['introduction','remedial_works','conclusion','cost_estimate']
PERSON_REFERENCES=['prepared_by_id','reviewed_by_id']
RATINGS=['element','condition_rating','likelihood','severity','priority']

class RevisionConflict(ValueError):pass

def atomic_json(path,value):
    temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2); f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('Invalid identifier')
    return value

def library_digest(library):
    content=json.dumps(library,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return hashlib.sha256(content).hexdigest()

def read_library_xlsx(content):
    """Read enabled wording rows from the editable common library."""
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
        # Replace the untouched 0.1.1 preset on upgrade; custom imports/edits keep their wording.
        if library_digest(self.library)==LIBRARY_POLICY['legacy_default_sha256']:
            self.library=json.loads((RESOURCES/'library.json').read_text(encoding='utf-8'))
            atomic_json(self.library_path,self.library)
            if (self.path/'library.xlsx').exists():
                shutil.copyfile(RESOURCES/'word_library.xlsx',self.path/'library.xlsx')
        self.options=json.loads((RESOURCES/'options.json').read_text(encoding='utf-8'))
        self.options.update(deepcopy(DEFAULT_RATING_OPTIONS))
        self.catalog_path=self.path/'photos.json'
        self.catalog=json.loads(self.catalog_path.read_text(encoding='utf-8')) if self.catalog_path.exists() else {}
        self.personnel_path=self.path/'personnel.json'
        if not self.personnel_path.exists():shutil.copyfile(RESOURCES/'personnel.json',self.personnel_path)
        self.personnel=json.loads(self.personnel_path.read_text(encoding='utf-8'))
        self.previews=PreviewManager(self,RESOURCES)

    def save_personnel(self,value):
        with self.lock:
            if not isinstance(value,dict) or not isinstance(value.get('people'),list) or len(value['people'])>200:
                raise ValueError('人员库格式不正确，最多 200 人')
            if type(value.get('revision')) is not int or value['revision']!=self.personnel['revision']:
                raise ValueError('人员库已在其他页面更新，请关闭后重新打开人员库')
            people=[];ids=set();names=set()
            for person in value['people']:
                if not isinstance(person,dict):raise ValueError('人员资料格式不正确')
                pid=identifier(person.get('id'))
                if pid in ids:raise ValueError('人员编号重复')
                fields={}
                for key in ['name','qualifications','title']:
                    text=person.get(key,'')
                    if not isinstance(text,str) or len(text)>500:raise ValueError('人员姓名、资质和职位最多 500 字符')
                    fields[key]=text.strip()
                if not fields['name']:raise ValueError('请填写姓名')
                if fields['name'].casefold() in names:raise ValueError('姓名重复，请编辑已有人员或填写可区分的姓名')
                roles=person.get('roles')
                if not isinstance(roles,list) or not roles or any(r not in ['author','reviewer'] for r in roles):
                    raise ValueError('请选择作者或审阅者角色')
                ids.add(pid);names.add(fields['name'].casefold())
                people.append({'id':pid,**fields,'roles':sorted(set(roles))})
            saved={'revision':value['revision']+1,'people':people}
            shutil.copyfile(self.personnel_path,self.path/'backups/personnel.previous.json')
            atomic_json(self.personnel_path,saved);self.personnel=saved
            return saved

    def path_for_project(self,pid):return self.path/'projects'/(identifier(pid)+'.json')
    def load(self,pid):
        path=self.path_for_project(pid)
        if not path.exists():raise ValueError('找不到这份草稿')
        project=json.loads(path.read_text(encoding='utf-8'))
        project.setdefault('sections',dict.fromkeys(SECTION_FIELDS,''))
        project.setdefault('cost_rows',[])
        return normalize_project(project)

    def list(self):
        result=[]
        for path in (self.path/'projects').glob('*.json'):
            p=json.loads(path.read_text(encoding='utf-8'))
            result.append({'id':p['id'],'site':p['metadata']['site'],'report_number':p['metadata']['report_number'],'updated':p['updated'],'count':len(p['items'])})
        return sorted(result,key=lambda p:p['updated'],reverse=True)

    def new(self):
        p={'id':secrets.token_hex(16),'revision':0,'updated':datetime.now().isoformat(timespec='seconds'),
           'metadata':dict.fromkeys(METADATA,''),'sections':dict.fromkeys(SECTION_FIELDS,''),'cost_rows':[],'items':[],'editor':blank_item(),'editor_id':None,'schema_version':2}
        p['metadata'].update({'client':'Town of Port Hedland','revision':'A','purpose':'Information','report_date':date.today().isoformat()})
        atomic_json(self.path_for_project(p['id']),p);return p

    def validate(self,p):
        identifier(p['id'])
        validate_rows(p.setdefault('cost_rows',[]))
        sections=p.setdefault('sections',dict.fromkeys(SECTION_FIELDS,''))
        if not isinstance(sections,dict):raise ValueError('报告章节格式不正确')
        for key in SECTION_FIELDS:
            value=sections.setdefault(key,'')
            if not isinstance(value,str) or len(value)>60000:raise ValueError('每个报告章节最多 60000 字符')
        if not isinstance(p.get('metadata'),dict) or not isinstance(p.get('items'),list) or len(p['items'])>1000:raise ValueError('草稿格式不正确')
        normalize_project(p)
        for key in METADATA:
            value=p['metadata'].get(key,'')
            if not isinstance(value,str) or len(value)>500:raise ValueError('报告信息过长')
        for key in PERSON_REFERENCES:
            if p['metadata'].get(key):identifier(p['metadata'][key])
        date.fromisoformat(p['metadata']['report_date'])
        itemids=set()
        for index,item in enumerate([*p['items'],p.get('editor',{})]):
            saved=index<len(p['items'])
            for key in RATINGS:
                if not isinstance(item.get(key,''),str) or len(item.get(key,''))>15000:raise ValueError('检查项文字过长')
            groups=item.get('subitems')
            if not isinstance(groups,list) or not 1<=len(groups)<=100:raise ValueError('每个检查项需要 1 至 100 个子项')
            groupids=set();photo_count=0
            for group in groups:
                if not isinstance(group,dict):raise ValueError('子项格式不正确')
                gid=identifier(group.get('id'))
                if gid in groupids:raise ValueError('子项编号重复')
                groupids.add(gid)
                for key in ['observation','recommendation']:
                    if not isinstance(group.get(key,''),str) or len(group.get(key,''))>15000:raise ValueError('检查项文字过长')
                photos=group.get('photos',[])
                if not isinstance(photos,list):raise ValueError('子项照片格式不正确')
                photo_count+=len(photos)
                if photo_count>100:raise ValueError('每个检查项最多 100 张照片')
                for photo in photos:
                    pid=identifier(photo['id'])
                    if pid not in self.catalog:raise ValueError('照片不存在，请重新导入')
                    photo['name']=self.catalog[pid]['name']
                    caption=photo.get('caption','')
                    if not isinstance(caption,str) or len(caption)>200:raise ValueError('照片名称最多 200 字符')
                    photo['caption']=caption.strip()
                if saved and (not photos or not group.get('observation','').strip()):raise ValueError('每个子项需要照片和 Observation')
            if saved:
                iid=identifier(item['id'])
                if iid in itemids:raise ValueError('检查项编号重复')
                itemids.add(iid)
                if any(not item.get(k,'').strip() for k in RATINGS):raise ValueError('检查项缺少照片、Observation 或评级')

    def save(self,p):
        with self.lock:
            self.validate(p);path=self.path_for_project(p['id']);existing=self.load(p['id'])
            if type(p.get('revision')) is not int or existing['revision']!=p['revision']:raise RevisionConflict('草稿已在其他页面更新。请先保留当前修改，再加载最新版本。')
            for key,prefix in [('prepared_by','author'),('reviewed_by','reviewer')]:
                ref=key+'_id'
                if existing['metadata'].get(ref) and (not p['metadata'].get(ref) or (p['metadata'].get(ref)==existing['metadata'].get(ref) and p['metadata'][key]!=existing['metadata'][key])):
                    p['metadata'][ref]='';p['metadata'][prefix+'_qualifications']='';p['metadata'][prefix+'_title']=''
            backup=self.path/'backups'/(p['id']+'.previous.json');shutil.copyfile(path,backup)
            p['revision']+=1;p['updated']=datetime.now().isoformat(timespec='seconds');atomic_json(path,p)
            return p

    def copy_project(self,p):
        with self.lock:
            p=deepcopy(p);self.validate(p)
            p['id']=secrets.token_hex(16);p['revision']=0;p['updated']=datetime.now().isoformat(timespec='seconds')
            atomic_json(self.path_for_project(p['id']),p)
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

    def edit_photo(self,pid,operations):
        from PIL import ImageDraw
        import math
        if not isinstance(operations,list) or not 1<=len(operations)<=50:raise ValueError('请先裁剪或添加标注，最多 50 步')
        with self.lock:
            pid=identifier(pid);old=self.catalog[pid]
            with Image.open(self.photo_path(pid)) as source:image=source.convert('RGB')
            for operation in operations:
                if not isinstance(operation,dict) or operation.get('type') not in ['crop','circle','rectangle','arrow','pen','rotate']:raise ValueError('不支持的照片编辑操作')
                kind=operation['type']
                if kind=='rotate':
                    if type(operation.get('turn')) is not int or operation['turn'] not in [-1,1]:raise ValueError('旋转方向无效')
                    image=image.transpose(Image.Transpose.ROTATE_270 if operation['turn']==1 else Image.Transpose.ROTATE_90)
                    continue
                color=operation.get('color','#e32636');width=operation.get('width',max(2,round(min(image.size)/150)))
                if color not in ['#e32636','#f5c400','#1677ff','#ffffff','#222222']:raise ValueError('标注颜色无效')
                if type(width) is not int or not 1<=width<=60:raise ValueError('标注线宽无效')
                draw=ImageDraw.Draw(image)
                if kind=='pen':
                    points=operation.get('points')
                    if not isinstance(points,list) or not 2<=len(points)<=2000:raise ValueError('画笔轨迹无效')
                    if any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in points):raise ValueError('画笔轨迹无效')
                    points=[tuple(round(v) for v in p) for p in points]
                    if any(not 0<=x<image.width or not 0<=y<image.height for x,y in points):raise ValueError('画笔轨迹超出照片范围')
                    draw.line(points,fill=color,width=width,joint='curve')
                    continue
                box=operation.get('box')
                if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box):raise ValueError('编辑区域无效')
                x0,y0,x1,y1=[round(v) for v in box]
                if kind=='arrow':
                    if not all(0<=x<image.width and 0<=y<image.height for x,y in [(x0,y0),(x1,y1)]) or math.hypot(x1-x0,y1-y0)<3:raise ValueError('箭头区域无效')
                    draw.line((x0,y0,x1,y1),fill=color,width=width)
                    angle=math.atan2(y1-y0,x1-x0);length=min(math.hypot(x1-x0,y1-y0)*.4,max(12,width*4))
                    wings=[(x1-length*math.cos(angle+a),y1-length*math.sin(angle+a)) for a in [-.5,.5]]
                    draw.line([wings[0],(x1,y1),wings[1]],fill=color,width=width,joint='curve')
                    continue
                if not 0<=x0<x1<=image.width or not 0<=y0<y1<=image.height:raise ValueError('编辑区域超出照片范围')
                if kind=='crop':
                    if x1-x0<10 or y1-y0<10:raise ValueError('裁剪区域太小')
                    image=image.crop((x0,y0,x1,y1))
                elif kind=='rectangle':draw.rectangle((x0,y0,x1-1,y1-1),outline=color,width=width)
                else:draw.ellipse((x0,y0,x1-1,y1-1),outline=color,width=width)
            new=secrets.token_hex(16)
            image.save(self.photo_path(new),'JPEG',quality=92)
            shutil.copyfile(self.path/'originals'/(pid+old['original_ext']),self.path/'originals'/(new+old['original_ext']))
            self.catalog[new]={**old,'id':new,'width':image.width,'height':image.height}
            atomic_json(self.catalog_path,self.catalog)
            return {'id':new,'name':old['name']}

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

    def report_snapshot(self,pid):
        with self.lock:
            p=self.load(pid);self.validate(p)
            if not p['items']:raise ValueError('请先保存至少一个检查项')
            if any(not p['metadata'].get(k,'').strip() for k in ['site','report_number','project_number']):raise ValueError('请先填写地点、报告编号和项目编号')
            return deepcopy(p)

    def export_snapshot(self,p):
        eid=secrets.token_hex(16);path=self.path/'exports'/(eid+'.docx')
        generate_report(RESOURCES/'report_template.docx',p,self.photo_path,path)
        name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',p['metadata']['report_number']+'_REV'+p['metadata']['revision']+'-'+p['metadata']['site'])[:170]+'.docx'
        return {'id':eid,'name':name}

    def export(self,pid):return self.export_snapshot(self.report_snapshot(pid))

    def preview(self,pid):
        return self.previews.start(self.report_snapshot(pid))

    def backup(self,pid):
        return self.backup_snapshot(self.load(pid))

    def backup_snapshot(self,p):
        with self.lock:
            p=deepcopy(p);self.validate(p)
            photoids={ph['id'] for item in [*p['items'],p['editor']] for ph in all_photos(item)}
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
            p=normalize_project(json.loads(z.read('project.json')));photos=json.loads(z.read('photos.json'))
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
                for ph in all_photos(item):ph['id']=mapping[ph['id']]
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
            language=query.get('lang',[''])[0]
            destination='/?lang='+language if language in ['en','zh'] else '/'
            self.send_response(302);self.send_header('Set-Cookie',f'workbench={self.server.token}; HttpOnly; SameSite=Strict; Path=/');self.send_header('Location',destination);self.end_headers();return
        if not self.authorized():self.reply({'error':'请从程序启动的页面打开工作台'},403);return
        try:
            s=self.server.store
            if url.path=='/api/bootstrap':self.reply({'library':s.library,'options':s.options,'personnel':s.personnel,'projects':s.list(),'data_folder':str(s.path),'version':__version__,'edition':UI_CONFIG['edition'],'preview_capability':word_capability()});return
            if url.path=='/api/preview-job':self.reply(s.previews.get(identifier(query['id'][0])));return
            if url.path=='/api/preview-capability':self.reply(word_capability());return
            if url.path=='/api/personnel':self.reply(s.personnel);return
            if url.path=='/api/project':self.reply(s.load(query['id'][0]));return
            if url.path.startswith('/photos/'):
                pid=url.path.split('/')[-1].removesuffix('.jpg');self.send_bytes(s.photo_path(pid).read_bytes(),'image/jpeg');return
            if url.path=='/api/download':
                eid=identifier(query['id'][0]);path=s.path/'exports'/(eid+'.docx')
                self.send_bytes(path.read_bytes(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename=query.get('name',['report.docx'])[0]);return
            if url.path=='/api/preview-pdf':
                eid=identifier(query['id'][0]);self.send_bytes((s.path/'exports'/(eid+'.pdf')).read_bytes(),'application/pdf');return
            if url.path=='/api/preview-page':
                eid=identifier(query['id'][0]);page=int(query['page'][0])
                if page<1:raise ValueError('页码无效')
                self.send_bytes((s.path/'exports'/f'{eid}-{page}.jpg').read_bytes(),'image/jpeg');return
            if url.path=='/api/backup':self.send_bytes(s.backup(query['id'][0]),'application/zip',filename='inspection-draft.inspection.zip');return
            if url.path=='/api/library-file':
                source=s.path/'library.xlsx'
                if not source.exists():source=RESOURCES/'word_library.xlsx'
                self.send_bytes(source.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename='word-library.xlsx');return
            file={'/':'index.html','/app.js':'app.js','/draft-state.js':'draft-state.js','/interface.js':'interface.js','/i18n.js':'i18n.js','/translations-en.js':'translations-en.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}.get(url.path)
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
            if path=='/api/project-copy':self.reply(s.copy_project(json.loads(content)));return
            if path=='/api/recovery-backup':self.send_bytes(s.backup_snapshot(json.loads(content)),'application/zip',filename='unsaved-draft.inspection.zip');return
            if path=='/api/personnel':self.reply(s.save_personnel(json.loads(content)));return
            if path=='/api/photo':self.reply(s.upload(content,unquote(self.headers.get('X-Filename','photo.jpg'))));return
            if path=='/api/rotate':self.reply(s.rotate(json.loads(content)['id']));return
            if path=='/api/photo-edit':
                edit=json.loads(content);self.reply(s.edit_photo(edit['id'],edit['operations']));return
            if path=='/api/save':self.reply(s.save(json.loads(content)));return
            if path=='/api/generate':self.reply(s.export(json.loads(content)['id']));return
            if path=='/api/preview':self.reply(s.preview(json.loads(content)['id']));return
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
        except RevisionConflict as exc:self.reply({'error':str(exc),'code':'revision_conflict'},409)
        except Exception as exc:
            logging.exception('POST failure');self.reply({'error':str(exc)},400)

def default_data_folder():
    base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    data_name='WorkbenchDataEnglish' if UI_CONFIG['edition']=='english' else 'WorkbenchData'
    preferred=base/data_name
    try:
        preferred.mkdir(exist_ok=True);probe=preferred/'.write-test';probe.write_text('test');probe.unlink();return preferred
    except OSError:
        return Path(os.environ.get('LOCALAPPDATA',Path.home()))/('WMLInspectionWorkbenchEnglish' if UI_CONFIG['edition']=='english' else 'WMLInspectionWorkbench')

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
        server.store.previews.close()
        server.server_close()
        if statepath.exists():statepath.unlink()

if __name__=='__main__':
    try:main()
    except Exception:
        logging.exception('Startup failure')
        if getattr(sys,'frozen',False):
            import ctypes
            message='Workbench failed to start. Check WorkbenchDataEnglish/workbench.log next to the program.' if UI_CONFIG['edition']=='english' else '工作台启动失败。请检查程序目录中的 WorkbenchData/workbench.log。'
            ctypes.windll.user32.MessageBoxW(None,message,'Inspection Workbench',16)
        else:raise
