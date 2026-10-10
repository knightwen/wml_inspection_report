"""Shared paths and validation for Windows portable builds."""
from pathlib import Path
import platform
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT / 'workbench/version.py'))['__version__']
OUTPUT = ROOT / 'outputs' / f'workbench_v{VERSION}'
ARCHIVE = ROOT / 'outputs' / f'InspectionWorkbench_v{VERSION}_Windows_x64.zip'


def require_windows_x64():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64') or sys.maxsize <= 2**32:
        raise SystemExit('Build with Windows x64 and 64-bit Python 3.12.')
    if sys.version_info[:2] != (3, 12):
        raise SystemExit('This distribution requires Python 3.12.')


if __name__ == '__main__':
    # A mistyped release tag must not mislabel the ZIP.
    if len(sys.argv) > 1 and sys.argv[1] != f'v{VERSION}':
        raise SystemExit(f'Release tag must be v{VERSION}; got {sys.argv[1]}')
    print(VERSION)
