"""Snapshot-based background preview and ownership-checked Word conversion."""
from copy import deepcopy
from pathlib import Path
import ctypes,json,logging,os,secrets,subprocess,threading,time
from report_types import report_type


def word_capability():
    if os.name!='nt' or os.environ.get('WML_DISABLE_WORD_PREVIEW')=='1':
        return {'available':False,'reason':'报告预览需要 Windows 和 Microsoft Word；仍可编辑草稿和生成 Word 报告。'}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r'Word.Application\CLSID'):pass
    except OSError:
        return {'available':False,'reason':'未检测到 Microsoft Word；仍可编辑草稿和生成 Word 报告。'}
    return {'available':True,'reason':'使用本机 Microsoft Word 转换实际分页。'}


def excel_capability():
    if os.name!='nt' or os.environ.get('WML_DISABLE_EXCEL_PREVIEW')=='1':
        return {'available':False,'reason':'CAL 打印预览需要桌面 Excel / CAL print preview requires desktop Excel.'}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r'Excel.Application\CLSID'):pass
    except OSError:
        return {'available':False,'reason':'未检测到桌面 Excel；仍可导出 Excel 和 Word / Desktop Excel not detected; XLSX and DOCX export remain available.'}
    return {'available':True,'reason':'使用桌面 Excel 打印版式 / Uses desktop Excel print layout.'}


def cleanup_owned_word(owner,executable='winword.exe'):
    """Never terminate an existing/reused Word process or a recycled process ID."""
    if os.name!='nt' or not owner.exists():return
    try:
        info=json.loads(owner.read_text(encoding='utf-8-sig'))
        if info.get('owned') is not True:return
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.GetProcessTimes.argtypes=[ctypes.c_void_p,*([ctypes.c_void_p]*4)]
        kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_wchar_p,ctypes.c_void_p]
        kernel.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        handle=kernel.OpenProcess(0x1000|1,False,int(info['pid']))
        if not handle:return
        try:
            created,ended,cpu,user=(ctypes.c_ulonglong() for _ in range(4))
            if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(ended),ctypes.byref(cpu),ctypes.byref(user)):return
            if str(created.value)!=str(info['creation_time']):return
            name=ctypes.create_unicode_buffer(32768);size=ctypes.c_ulong(len(name))
            if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)):return
            if Path(name.value).name.casefold()==executable:kernel.TerminateProcess(handle,1)
        finally:kernel.CloseHandle(handle)
    except Exception:logging.exception('Owned Word cleanup failed')


def convert_word_pdf(source,resources,cancel,timeout=120):
    owner=source.with_suffix('.word-owner.json')
    command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(resources/'preview_report.ps1'),str(source.resolve()),str(owner.resolve())]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    started=time.monotonic()
    try:
        while process.poll() is None:
            if cancel.is_set() or time.monotonic()-started>timeout:
                process.kill();process.communicate()
                raise ValueError('报告预览已取消。' if cancel.is_set() else 'Word 转换超时，已清理本次转换；可重试或直接生成 Word 报告。')
            time.sleep(.1)
        _,error=process.communicate()
        pdf=source.with_suffix('.pdf')
        if process.returncode or not pdf.exists() or not pdf.read_bytes().startswith(b'%PDF-'):
            logging.error('Word preview conversion failed: %r',error)
            raise ValueError('Word 转换失败，请确认已安装并激活 Microsoft Word；可以重试，或直接生成 Word 报告。')
        return pdf
    finally:
        if process.poll() is None:process.kill();process.communicate()
        cleanup_owned_word(owner)


def convert_excel_pdf(source,resources,cancel,timeout=120):
    owner=source.with_suffix('.excel-owner.json')
    command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(resources/'preview_calculation.ps1'),str(source.resolve()),str(owner.resolve()),str((resources/'wml-logo.png').resolve())]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    started=time.monotonic()
    try:
        while process.poll() is None:
            if cancel.is_set() or time.monotonic()-started>timeout:
                process.kill();process.communicate()
                raise ValueError('Excel 转换已取消或超时，请重试 / Excel conversion cancelled or timed out; please retry.')
            request=source.with_suffix('.toc-request.json');response=source.with_suffix('.toc.json')
            if request.exists() and not response.exists():
                try:
                    payload=json.loads(request.read_text(encoding='utf-8-sig'))
                except (ValueError,OSError):
                    time.sleep(.1);continue
                numbers=printed_contents_pages(source,payload['headings'])
                temporary=response.with_suffix('.tmp')
                temporary.write_text(json.dumps(numbers),encoding='utf-8');temporary.replace(response)
            time.sleep(.1)
        _,error=process.communicate()
        pdf=source.with_suffix('.pdf')
        if process.returncode or not pdf.exists() or not pdf.read_bytes().startswith(b'%PDF-'):
            logging.error('Excel preview conversion failed: %r',error)
            raise ValueError('Excel 转换失败，请确认桌面 Excel 可用 / Excel conversion failed; check desktop Excel.')
        return pdf
    finally:
        if process.poll() is None:process.kill();process.communicate()
        cleanup_owned_word(owner,'excel.exe')
        for suffix in ['.toc-request.json','.toc.json','.report.pdf']:
            source.with_suffix(suffix).unlink(missing_ok=True)


def printed_contents_pages(source,headings):
    """Locate chapter labels in Excel's printed Report sheet, in document order."""
    import re
    import pypdfium2 as pdfium
    normalize=lambda text:re.sub(r'\s+','',text).casefold()
    pages=[]
    with pdfium.PdfDocument(str(source.with_suffix('.pdf'))) as full, pdfium.PdfDocument(str(source.with_suffix('.report.pdf'))) as report:
        offset=len(full)-len(report)
        for page in report:
            textpage=page.get_textpage()
            try:
                text=textpage.get_text_range()
                pages.append(({normalize(line) for line in text.splitlines()},normalize(text)))
            finally:textpage.close();page.close()
    result=[];previous=0
    for heading in headings:
        title=normalize(heading['title'])
        found=next((i for i in range(previous,len(pages)) if title in pages[i][0]),None)
        if found is None:found=next((i for i in range(previous,len(pages)) if title in pages[i][1]),None)
        if found is None:
            raise ValueError('无法定位打印章节 / Cannot locate printed chapter: '+heading['title'])
        result.append({'row':heading['row'],'page':offset+found+1});previous=found
    return result


def render_pdf(pdf,source,progress,cancel):
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(str(pdf)) as document:
        total=len(document)
        for index in range(total):
            if cancel.is_set():raise ValueError('报告预览已取消。')
            page=document[index]
            try:
                bitmap=page.render(scale=1.3)
                try:bitmap.to_pil().save(source.with_name(f'{source.stem}-{index+1}.jpg'),'JPEG',quality=90)
                finally:bitmap.close()
            finally:page.close()
            progress(index+1,total)
    return total


class PreviewManager:
    def __init__(self,store,resources,converter=convert_word_pdf,renderer=render_pdf,capability=word_capability,excel_converter=convert_excel_pdf,excel_check=excel_capability):
        self.store=store;self.resources=resources;self.converter=converter;self.renderer=renderer;self.capability=capability
        self.excel_converter=excel_converter;self.excel_check=excel_check
        self.lock=threading.RLock();self.slots=threading.Semaphore(1);self.jobs={};self.cancel=threading.Event();self.threads=[]

    def update(self,jid,**values):
        with self.lock:self.jobs[jid].update(values)

    def get(self,jid):
        with self.lock:
            if jid not in self.jobs:raise ValueError('预览任务不存在，请重新预览。')
            return deepcopy(self.jobs[jid])

    def start(self,snapshot):
        capability=self.excel_check() if report_type(snapshot)=='calculation' else self.capability()
        if not capability['available']:raise ValueError(capability['reason'])
        with self.lock:
            if sum(j['status'] not in ['ready','failed'] for j in self.jobs.values())>=3:raise ValueError('已有预览任务在进行，请等待完成后重试。')
            jid=secrets.token_hex(16)
            job={'id':jid,'status':'queued','message':'等待预览转换…','project_id':snapshot['id'],'project_revision':snapshot['revision'],'site':snapshot['metadata']['site'],'pages':0,'pages_done':0}
            self.jobs[jid]=job
            # Bound status memory; exported reports remain available on disk.
            completed=[k for k,v in self.jobs.items() if v['status'] in ['ready','failed']]
            for old in completed[:-20]:del self.jobs[old]
        thread=threading.Thread(target=self.run,args=(jid,deepcopy(snapshot)),daemon=True)
        self.threads=[t for t in self.threads if t.is_alive()];self.threads.append(thread);thread.start()
        return self.get(jid)

    def run(self,jid,snapshot):
        with self.slots:
            try:
                if self.cancel.is_set():raise ValueError('报告预览已取消。')
                self.update(jid,status='generating',message='正在生成报告快照…')
                result=self.store.export_snapshot(snapshot)
                cal=report_type(snapshot)=='calculation'
                format='xlsx' if cal else 'docx'
                if cal:self.store.export_snapshot(snapshot,'docx',export_id=result['id'])
                self.update(jid,report_id=result['id'],name=result['name'],format=format,status='converting',message='正在使用 Excel 转换打印分页 / Paginating with Excel…' if cal else '正在使用 Word 转换分页…')
                source=self.store.path/'exports'/(result['id']+'.'+format)
                pdf=(self.excel_converter if cal else self.converter)(source,self.resources,self.cancel)
                self.update(jid,status='rendering',message='正在渲染预览页面…')
                def progress(done,total):self.update(jid,pages_done=done,pages=total,message=f'正在渲染第 {done} / {total} 页…')
                count=self.renderer(pdf,source,progress,self.cancel)
                self.update(jid,status='ready',message='预览已完成',pages=count,pages_done=count)
            except Exception as error:
                logging.exception('Preview job failed')
                self.update(jid,status='failed',message=str(error),error=str(error))

    def close(self):
        self.cancel.set()
        for thread in self.threads:thread.join(timeout=2)
