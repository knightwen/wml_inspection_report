"""Build a Windows portable EXE using the active Python environment."""
import os
from distribution import ROOT, OUTPUT, VERSION, require_windows_x64


def main():
    require_windows_x64()
    os.environ['PYINSTALLER_CONFIG_DIR'] = str(ROOT / '.build/pyinstaller-cache')
    from PyInstaller.__main__ import run
    run([
        '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', 'InspectionWorkbench',
        '--distpath', str(OUTPUT),
        '--workpath', str(ROOT / '.build' / f'pyinstaller-v{VERSION}'),
        '--specpath', str(ROOT / '.build'),
        '--paths', str(ROOT / 'workbench'),
        '--add-data', str(ROOT / 'workbench/web') + ':web',
        '--add-data', str(ROOT / 'workbench/resources') + ':resources',
        '--collect-all', 'pillow_heif',
        '--collect-all', 'pypdfium2',
        '--collect-all', 'pypdfium2_raw',
        '--exclude-module', 'numpy', '--exclude-module', 'scipy',
        '--exclude-module', 'matplotlib', '--exclude-module', 'pandas',
        '--exclude-module', 'torch', '--exclude-module', 'tkinter',
        str(ROOT / 'workbench/app.py'),
    ])
    print(f'Executable: {OUTPUT / "InspectionWorkbench.exe"}')


if __name__ == '__main__':
    main()
