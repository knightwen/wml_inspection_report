"""Assemble a portable ZIP from a clean checkout and the active environment."""
import argparse
import concurrent.futures
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

from distribution import ROOT, VERSION, require_windows_x64, edition_paths


def copy_licenses(target):
    shutil.copytree(ROOT / 'LICENSES', target, dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'LICENSE', target / 'Application.txt')
    shutil.copyfile(Path(sys.base_prefix) / 'LICENSE.txt', target / 'Python.txt')
    versions = {}
    for name in ('Pillow', 'pillow-heif', 'lxml', 'pypdfium2', 'PyInstaller', 'pyinstaller-hooks-contrib'):
        dist = importlib.metadata.distribution(name)
        versions[name] = dist.version
        files = [f for f in dist.files or [] if '.dist-info/licenses/' in str(f).replace('\\', '/')]
        if not files:
            raise RuntimeError(f'Missing installed licenses for {name}')
        for f in files:
            relative = str(f).replace('\\', '/').split('.dist-info/licenses/', 1)[1]
            dest = target / name / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dist.locate_file(f), dest)
    return versions


def download_source(entry):
    cache = ROOT / '.build/source-cache' / entry['file']
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and hashlib.sha256(cache.read_bytes()).hexdigest() == entry['sha256']:
        return cache
    for attempt in range(3):
        try:
            request = urllib.request.Request(entry['url'], headers={'User-Agent': 'InspectionWorkbench-Packaging'})
            with urllib.request.urlopen(request, timeout=45) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise RuntimeError(f'Source checksum mismatch: {entry["file"]}')
            temporary = cache.with_suffix('.tmp')
            temporary.write_bytes(content)
            temporary.replace(cache)
            return cache
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def package(edition='bilingual'):
    require_windows_x64()
    name,output,archive_path=edition_paths(edition)
    exe = output / (name+'.exe')
    if not exe.is_file():
        raise SystemExit('EXE missing. Run python tools/build_workbench.py first, or use --build.')
    import pillow_heif
    source_config = json.loads((ROOT / 'tools/heic_sources.json').read_text(encoding='utf-8'))
    heic = pillow_heif.libheif_info()
    if importlib.metadata.version('pillow-heif') != source_config['pillow-heif'] or heic != source_config['runtime']:
        raise RuntimeError('HEIC wheel changed. Review and update tools/heic_sources.json before distribution.')
    # Stage only explicit deliverables; never sweep personal drafts or old output into the ZIP.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-', dir=ROOT / '.build') as temporary:
        stage = Path(temporary) / name
        stage.mkdir()
        shutil.copyfile(exe, stage / exe.name)
        versions = copy_licenses(stage / 'LICENSES')
        source = stage / 'source'
        for directory in ('web', 'resources'):
            shutil.copytree(ROOT / 'workbench' / directory, source / 'workbench' / directory)
        for file in (ROOT / 'workbench').glob('*.py'):
            shutil.copyfile(file, source / 'workbench' / file.name)
        for file in ('README.md', 'requirements.txt', 'LICENSE'):
            shutil.copyfile(ROOT / file, source / file)
        source_tools = source / 'tools'
        source_tools.mkdir()
        for tool_name in ('build_workbench.py', 'package_workbench.py', 'distribution.py', 'prepare_english_assets.py', 'test_english_assets.py', 'smoke_frozen_workbench.py', 'validate_reports.ps1', 'heic_sources.json', 'build_common_word_library.mjs','test_draft_state.cjs','test_i18n.cjs','test_browser_workbench.cjs','browser_test_server.py','test_native_preview.py'):
            shutil.copyfile(ROOT / 'tools' / tool_name, source_tools / tool_name)
        shutil.copytree(ROOT/'docs',source/'docs')
        shutil.copytree(stage / 'LICENSES', source / 'LICENSES')
        third = source / 'third_party'
        third.mkdir()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            archives = list(executor.map(download_source, source_config['sources']))
        for archive in archives:
            with tarfile.open(archive, 'r:gz') as bundle:
                if not bundle.getmembers():
                    raise RuntimeError(f'Empty source archive: {archive}')
            shutil.copyfile(archive, third / archive.name)
        (third / 'sources.json').write_text(json.dumps(source_config, indent=2), encoding='utf-8')
        (source / 'BUILD.txt').write_text(
            'Windows x64, Python 3.12. Install requirements.txt in a virtual environment.\n'
            f'Run: python tools/package_workbench.py --build --edition {edition}\n'
            'Upstream HEIC sources and build recipes are in third_party/.\n'
            'Unmodified PyPI wheels are used. Templates and wording remain separate user data.\n', encoding='utf-8')
        notices = {'application': VERSION, 'edition':edition, 'python': sys.version.split()[0], 'packages': versions, 'heic': heic}
        (stage / 'THIRD_PARTY_NOTICES.txt').write_text(
            'Preserve LICENSES/ and source/ when redistributing this portable program.\n'
            'Application: GPL-2.0-or-later. Templates, wording and user reports retain their ownership.\n\n'
            + json.dumps(notices, indent=2), encoding='utf-8')
        if edition=='english':
            (stage/'README.txt').write_text((ROOT/'docs/README_EN.md').read_text(encoding='utf-8'),encoding='utf-8')
        else:(stage / '使用说明.txt').write_text(
            f'检查报告工作台 {VERSION} · Windows 10/11 x64\n\n'
            '请先解压完整 ZIP，再双击 InspectionWorkbench.exe。首次启动需要几秒，会自动打开浏览器。\n'
            '无需安装 Python、Word 或照片编解码器；查看和编辑 DOCX 可使用 Word。\n\n'
            '实际分页预览需要本机已安装并激活 Microsoft Word；无 Word 仍可编辑草稿并生成 DOCX。\n'
            '预览在后台生成固定快照；可关闭预览窗口继续编辑，再查看进度和结果。\n'
            '下载此份 Word 对应当前预览，后续编辑不会改变这份快照。转换失败时可重试。\n\n'
            '填写报告信息 → 填写检查项共用评级 → 添加子项的照片和描述 → Save → Generate。\n'
            '每个子项支持多张照片、独立 Observation 和可留空的 Recommendation。\n'
            '子项支持增删、拖动排序；照片支持命名、裁剪和标注。完成后保存整个检查项。\n'
            'Word 连续编号每张照片，同一子项的右侧描述单元格纵向合并。当前编辑项必须先 Save 才会进入报告。\n'
            '报告中的空白章节需后续补充，Word 目录需更新整个目录。\n\n'
            '草稿、照片和报告保存在程序旁 WorkbenchData；目录不可写时保存到\n'
            '%LOCALAPPDATA%/WMLInspectionWorkbench。页面显示实际位置。\n'
            '跨电脑迁移请使用“备份草稿”和“导入草稿”，或保留并复制 WorkbenchData。\n'
            '升级前点击“退出程序”，解压新版并保留自己的 WorkbenchData。\n'
            '升级前备份草稿。旧草稿自动转为一个子项；含子项的新草稿需使用 0.1.5 或更高版本。\n'
            '关闭浏览器不会退出服务，请点击页面右上角“退出程序”。\n'
            '文字库支持下载 Excel 编辑后导入。\n\n'
            '保存状态会区分未保存、等待、保存中和失败。关闭页面前请等待已保存。\n'
            '发生多页面保存冲突时，可以另存副本或下载包含照片的当前修改备份，再加载最新草稿。\n'
            '从人员库切换到手动姓名会清除旧人员的资质与职位；既有报告快照不受人员库变更影响。\n\n'
            '分发给同事请保留 LICENSES 和 source；本 ZIP 不包含个人草稿或现场照片。\n', encoding='utf-8')
        pending = archive_path.with_suffix('.zip.tmp')
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(stage.rglob('*')):
                if file.is_file():
                    archive.write(file, file.relative_to(stage.parent).as_posix())
        pending.replace(archive_path)
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive_path.name}\n', encoding='ascii')
    print(f'Portable ZIP: {archive_path} ({archive_path.stat().st_size:,} bytes)')
    return archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Build the EXE, package and verify the final ZIP')
    parser.add_argument('--edition',choices=['bilingual','english'],default='bilingual')
    args = parser.parse_args()
    if args.build:
        subprocess.run([sys.executable, str(ROOT / 'tools/build_workbench.py'),'--edition',args.edition], check=True)
    archive = package(args.edition)
    if args.build:
        subprocess.run([sys.executable, str(ROOT / 'tools/smoke_frozen_workbench.py'), '--zip', str(archive),'--edition',args.edition], check=True)


if __name__ == '__main__':
    main()
