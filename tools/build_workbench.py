"""Build a Windows portable EXE using the active Python environment."""
import os
import argparse
import tempfile
from pathlib import Path
from distribution import ROOT, VERSION, require_windows_x64, edition_paths


def main():
    require_windows_x64()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--edition',choices=['bilingual','english'],default='bilingual');args=parser.parse_args()
    name,output,_=edition_paths(args.edition)
    os.environ['PYINSTALLER_CONFIG_DIR'] = str(ROOT / '.build/pyinstaller-cache')
    # Fresh work directories avoid deleting OneDrive-locked files from an earlier build.
    work = tempfile.mkdtemp(prefix=f'pyinstaller-v{VERSION}-', dir=ROOT / '.build')
    web,resources=ROOT/'workbench/web',ROOT/'workbench/resources'
    if args.edition=='english':
        from prepare_english_assets import prepare_english_assets
        web,resources=prepare_english_assets(Path(work)/'english-assets')
    from PyInstaller.__main__ import run
    run([
        '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', name,
        '--distpath', str(output),
        '--workpath', work,
        '--specpath', str(ROOT / '.build'),
        '--paths', str(ROOT / 'workbench'),
        '--add-data', str(web) + ':web',
        '--add-data', str(resources) + ':resources',
        '--collect-all', 'pillow_heif',
        '--collect-all', 'pypdfium2',
        '--collect-all', 'pypdfium2_raw',
        '--collect-data', 'docx',
        '--exclude-module', 'numpy', '--exclude-module', 'scipy',
        '--exclude-module', 'matplotlib', '--exclude-module', 'pandas',
        '--exclude-module', 'torch', '--exclude-module', 'tkinter',
        str(ROOT / 'workbench/app.py'),
    ])
    print(f'Executable: {output / (name+".exe")}')


if __name__ == '__main__':
    main()
