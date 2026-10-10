"""Assemble portable deliverables, attribution, and corresponding source archives."""
from pathlib import Path
import concurrent.futures,hashlib,json,shutil,sys,tarfile,urllib.request,zipfile
root=Path(__file__).resolve().parents[1]
out=root/'outputs/workbench_v0.1.1';licenses=out/'LICENSES';sources=out/'source';third=sources/'third_party'
for p in [licenses,sources,third]:p.mkdir(parents=True,exist_ok=True)
runtime=Path(sys.executable).parent
shutil.copyfile(runtime/'LICENSE.txt',licenses/'Python.txt')
for name,relative in [('Pillow','.build/vendor/pillow-12.3.0.dist-info/licenses/LICENSE'),('pillow-heif','.build/vendor/pillow_heif-1.8.0.dist-info/licenses/LICENSE.txt'),('HEIC-bundled','.build/vendor/pillow_heif-1.8.0.dist-info/licenses/LICENSES_bundled.txt'),('PyInstaller','.build/vendor/pyinstaller-6.22.3.dist-info/licenses/COPYING.txt')]:
    shutil.copyfile(root/relative,licenses/(name+'.txt'))
lxml=runtime/'Lib/site-packages/lxml-6.1.1.dist-info/licenses'
for f in lxml.rglob('*'):
    if f.is_file():shutil.copyfile(f,licenses/('lxml-'+f.name))
downloads=[('libheif-1.23.4.tar.gz','https://codeload.github.com/strukturag/libheif/tar.gz/refs/tags/v1.23.4'),('libde265-1.1.3.tar.gz','https://codeload.github.com/strukturag/libde265/tar.gz/refs/tags/v1.1.3'),('x265-4.2.tar.gz','https://bitbucket.org/multicoreware/x265_git/get/4.2.tar.gz'),('pillow-heif-1.8.0.tar.gz','https://codeload.github.com/bigcat88/pillow_heif/tar.gz/refs/tags/v1.8.0')]
def download(entry):
    name,url=entry;target=third/name
    if not target.exists():
        previous=root/'outputs/workbench_v0.1/source/third_party'/name
        if previous.exists():shutil.copyfile(previous,target)
    if not target.exists():
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'InspectionWorkbench-Packaging'}),timeout=30) as response:content=response.read()
        with tarfile.open(fileobj=__import__('io').BytesIO(content),mode='r:gz') as archive:assert archive.getmembers()
        target.write_bytes(content)
    return {'file':name,'url':url,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    records=list(executor.map(download,downloads))
(third/'sources.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
with tarfile.open(third/'x265-4.2.tar.gz','r:gz') as archive:
    member=next(m for m in archive.getmembers() if m.name.endswith('/COPYING'))
    gpl=archive.extractfile(member).read();(licenses/'GPL-2.0.txt').write_bytes(gpl)
with tarfile.open(third/'libheif-1.23.4.tar.gz','r:gz') as archive:
    for member in archive.getmembers():
        if member.isfile() and Path(member.name).name.startswith('COPYING'): (licenses/('libheif-'+Path(member.name).name+'.txt')).write_bytes(archive.extractfile(member).read())
for f in (root/'workbench').rglob('*'):
    if f.is_file() and f.suffix not in ['.pyc'] and '__pycache__' not in f.parts and 'WorkbenchData' not in f.parts:
        target=sources/'workbench'/f.relative_to(root/'workbench');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
(sources/'tools').mkdir(exist_ok=True)
shutil.copyfile(root/'tools/build_workbench.py',sources/'tools/build_workbench.py')
if (sources/'build_workbench.py').exists():(sources/'build_workbench.py').unlink()
(sources/'COPYING').write_bytes(gpl)
(sources/'BUILD.txt').write_text('Inspection Workbench 0.1.1 source\n\nThe application code is provided under GPL-2.0-or-later, without warranty. Report templates, wording-library data, photos and generated reports remain separate user data and are not relicensed.\n\nFor developer builds (end users need none of these): Windows x64, Python 3.12; Pillow==12.3.0, pillow-heif==1.8.0, lxml==6.1.1, PyInstaller==6.22.3, pyinstaller-hooks-contrib==2026.8.\nRun PyInstaller --onefile --windowed --name InspectionWorkbench --paths workbench --add-data "workbench/web;web" --add-data "workbench/resources;resources" --collect-all pillow_heif workbench/app.py.\nThe supplied third_party source archives contain the upstream HEIC components and build instructions. pillow-heif includes its native wheel build configuration, libheif/libde265 use CMake, and x265 includes CMake build instructions. Unmodified official binary wheels were used.\n',encoding='utf-8')
(out/'THIRD_PARTY_NOTICES.txt').write_text('Inspection Workbench 0.1.1\n\nPython 3.12.14 (PSF), Pillow 12.3.0 (HPND and bundled notices), lxml 6.1.1 (BSD and bundled notices), pillow-heif 1.8.0 (BSD source; GPLv2 wheel), libheif 1.23.4 (LGPLv3), libde265 1.1.3 (LGPLv3), x265 4.2 (GPLv2), MinGW runtimes (GCC runtime exception / MIT / BSD), PyInstaller 6.22.3 (GPL with bootloader exception).\n\nSee LICENSES for copyright and license texts. Application source and HEIC corresponding source archives accompany the portable program in source/. Preserve these files when redistributing. User report data and templates retain their existing ownership.\n',encoding='utf-8')
(out/'使用说明.txt').write_text('检查报告工作台 · 原型 0.1.1\n\n启动\n将整个文件夹放在自己的电脑上，双击 InspectionWorkbench.exe。首次启动需要几秒，会自动打开默认浏览器。Windows 10/11 64 位；无需安装 Python、照片编解码器或其他依赖。生成 DOCX 不需要安装 Word，后续查看和编辑报告可使用 Word。\n\n使用顺序\n1. 展开“报告信息”，填写地点、报告编号、项目编号及封面信息。\n2. 多张照片一起拖入左侧，或点击选择照片。支持 JPG、PNG、WEBP、HEIC、HEIF。一个检查项可放多张照片，可旋转、前移或后移。\n3. 填写 Element 和四项评级。菜单来自历史报告，也允许手动输入；评级之间不自动推算。\n4. 搜索文字库，选择 Observation / Recommendation，随后自由编辑；也可以直接输入。\n5. 点击 Save，检查项保存在下方。可重新编辑、删除、调整导出顺序。\n6. 所有检查项整理完，点击 Generate。报告自动下载，另存一份在 WorkbenchData/exports。当前编辑区需要先 Save 才会加入报告。\n7. 用 Word 打开报告，接受更新域的提示；如目录页码未显示，在目录上右键“更新域”→“更新整个目录”。\n\n模板与照片\n封面、文档信息、检查表、页脚使用提供的 Dempster Street Word 模板。Introduction、Recommended Remedial Works、Conclusion 和 Cost Estimate 保留空白，后续在 Word 中补充。多张照片在同一个检查表中按 1.1、1.2…编号，描述在第一张照片旁显示一次。原始照片单独保存，报告照片自动转 JPEG、纠正方向并缩小体积。\n\n草稿与备份\n编辑区和报告信息自动保存；下次启动可继续。点击“备份草稿”导出包含照片的 ZIP，另一台电脑可用“导入草稿”创建副本。请保留程序旁的 WorkbenchData 文件夹，它包含自己的草稿、原始照片和导出报告。通常可把程序和此文件夹一起迁移；如果程序目录无法写入，会改存到自己的 LocalAppData/WMLInspectionWorkbench，页面底部显示实际目录。关闭浏览器不会退出程序；请点页面右上角“退出程序”。再次双击正在运行的程序会重新打开页面。\n\n更新文字库\n点击“文字库”，下载当前 Excel；编辑 Observation、Recommendation 工作表第 7 行起的内容。A 列编号保持唯一，B 列“是”表示启用，C 列是描述，D 列是构件标签。新增行也按此结构填写。编辑好后重新导入。原始数据和待确认合并工作表不参与自动合并；当前 622 条 Observation 与 175 条 Recommendation 保持独立。导入新文字库不会改写已保存检查项。\n\n发给同事\n把完整便携包 ZIP 发给同事，解压后双击程序即可。每个人的数据独立，不需要账号。分发包不包含测试草稿、现场原图或历史报告全集。source 和 LICENSES 是程序源码及第三方说明，不需要安装。\n',encoding='utf-8')
(out/'更新说明.txt').write_text('0.1.1 版式修正\n\n恢复模板正文的分节边距、主要检查表列宽和描述段落格式，横向和竖向照片按同一照片列宽显示。纸张、封面、字体和页脚沿用原模板。\n\n更新：先在旧程序中点击退出程序。将新版 InspectionWorkbench.exe 替换旧程序，保留原目录中的 WorkbenchData 文件夹，双击新版后重新生成报告。旧报告不会自动修改。若保留独立新版目录，可先用旧程序导出草稿备份，再在新版导入。\n',encoding='utf-8')
destination=root/'outputs/InspectionWorkbench_v0.1.1_Windows_x64.zip'
with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
    for f in out.rglob('*'):
        if f.is_file() and 'WorkbenchData' not in f.parts:z.write(f,'InspectionWorkbench/'+str(f.relative_to(out)).replace('\\','/'))
print(json.dumps({'zip':str(destination),'bytes':destination.stat().st_size,'exe_bytes':(out/'InspectionWorkbench.exe').stat().st_size,'source_archives':records}))
