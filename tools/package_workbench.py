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

from distribution import ARCHIVE, OUTPUT, ROOT, VERSION, require_windows_x64


def copy_licenses(target):
    shutil.copytree(ROOT / 'LICENSES', target, dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'LICENSE', target / 'Application.txt')
    shutil.copyfile(Path(sys.base_prefix) / 'LICENSE.txt', target / 'Python.txt')
    versions = {}
    for name in ('Pillow', 'pillow-heif', 'lxml', 'PyInstaller', 'pyinstaller-hooks-contrib'):
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


def package():
    require_windows_x64()
    exe = OUTPUT / 'InspectionWorkbench.exe'
    if not exe.is_file():
        raise SystemExit('EXE missing. Run python tools/build_workbench.py first, or use --build.')
    import pillow_heif
    source_config = json.loads((ROOT / 'tools/heic_sources.json').read_text(encoding='utf-8'))
    heic = pillow_heif.libheif_info()
    if importlib.metadata.version('pillow-heif') != source_config['pillow-heif'] or heic != source_config['runtime']:
        raise RuntimeError('HEIC wheel changed. Review and update tools/heic_sources.json before distribution.')
    # Stage only explicit deliverables; never sweep personal drafts or old output into the ZIP.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-', dir=ROOT / '.build') as temporary:
        stage = Path(temporary) / 'InspectionWorkbench'
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
        for name in ('build_workbench.py', 'package_workbench.py', 'distribution.py', 'smoke_frozen_workbench.py', 'heic_sources.json'):
            shutil.copyfile(ROOT / 'tools' / name, source_tools / name)
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
            'Run: python tools/package_workbench.py --build\n'
            'Upstream HEIC sources and build recipes are in third_party/.\n'
            'Unmodified PyPI wheels are used. Templates and wording remain separate user data.\n', encoding='utf-8')
        notices = {'application': VERSION, 'python': sys.version.split()[0], 'packages': versions, 'heic': heic}
        (stage / 'THIRD_PARTY_NOTICES.txt').write_text(
            'Preserve LICENSES/ and source/ when redistributing this portable program.\n'
            'Application: GPL-2.0-or-later. Templates, wording and user reports retain their ownership.\n\n'
            + json.dumps(notices, indent=2), encoding='utf-8')
        (stage / '使用说明.txt').write_text(
            f'检查报告工作台 {VERSION} · Windows 10/11 x64\n\n'
            '请先解压完整 ZIP，再双击 InspectionWorkbench.exe。首次启动需要几秒，会自动打开浏览器。\n'
            '无需安装 Python、Word 或照片编解码器；查看和编辑 DOCX 可使用 Word。\n\n'
            '填写报告信息 → 拖入照片 → 填写评级和 Observation / Recommendation → Save → Generate。\n'
            '每个检查项支持多张照片，可旋转和排序。当前编辑项必须先 Save 才会进入报告。\n'
            '报告中的空白章节需后续补充，Word 目录需更新整个目录。\n\n'
            '草稿、照片和报告保存在程序旁 WorkbenchData；目录不可写时保存到\n'
            '%LOCALAPPDATA%/WMLInspectionWorkbench。页面显示实际位置。\n'
            '跨电脑迁移请使用“备份草稿”和“导入草稿”，或保留并复制 WorkbenchData。\n'
            '升级前点击“退出程序”，解压新版并保留自己的 WorkbenchData。\n'
            '关闭浏览器不会退出服务，请点击页面右上角“退出程序”。\n'
            '文字库支持下载 Excel 编辑后导入。\n\n'
            '分发给同事请保留 LICENSES 和 source；本 ZIP 不包含个人草稿或现场照片。\n', encoding='utf-8')
        pending = ARCHIVE.with_suffix('.zip.tmp')
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(stage.rglob('*')):
                if file.is_file():
                    archive.write(file, file.relative_to(stage.parent).as_posix())
        pending.replace(ARCHIVE)
    checksum = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    ARCHIVE.with_suffix('.zip.sha256').write_text(f'{checksum}  {ARCHIVE.name}\n', encoding='ascii')
    print(f'Portable ZIP: {ARCHIVE} ({ARCHIVE.stat().st_size:,} bytes)')
    return ARCHIVE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Build the EXE, package and verify the final ZIP')
    args = parser.parse_args()
    if args.build:
        subprocess.run([sys.executable, str(ROOT / 'tools/build_workbench.py')], check=True)
    archive = package()
    if args.build:
        subprocess.run([sys.executable, str(ROOT / 'tools/smoke_frozen_workbench.py'), '--zip', str(archive)], check=True)


if __name__ == '__main__':
    main()
