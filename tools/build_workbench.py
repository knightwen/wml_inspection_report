"""Build an offline Windows x64 executable using task-local packaging dependencies."""
import sys,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.build/vendor'))
os.environ['PYINSTALLER_CONFIG_DIR']=str(root/'.build/pyinstaller-cache')
from PyInstaller.__main__ import run
run(['--noconfirm','--clean','--onefile','--windowed','--name','InspectionWorkbench',
     '--distpath',str(root/'outputs/workbench_v0.1.1'),
     '--workpath',str(root/'.build/pyinstaller-v011'),
     '--specpath',str(root/'.build'),
     '--paths',str(root/'workbench'),
     '--add-data',str(root/'workbench/web')+';web',
     '--add-data',str(root/'workbench/resources')+';resources',
     '--collect-all','pillow_heif',
     '--exclude-module','numpy','--exclude-module','scipy','--exclude-module','matplotlib',
     '--exclude-module','pandas','--exclude-module','torch','--exclude-module','tkinter',
     str(root/'workbench/app.py')])
