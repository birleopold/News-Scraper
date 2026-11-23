"""Where the app's own files and your data live.

Run from the project folder (python run.py): everything is in the folder, data in ./data.
Installed with UgandaBusinessWatch-Setup.exe: the program files are read-only and data
goes to %LOCALAPPDATA%\\UgandaBusinessWatch\\data, which the uninstaller keeps.
UGW_DATA_DIR overrides the data folder in both cases (e.g. for a USB stick or testing).
"""
import os
import sys
from pathlib import Path

APP_NAME = 'UgandaBusinessWatch'


def frozen():
    """True when running as the packaged UgandaBusinessWatch.exe."""
    return bool(getattr(sys, 'frozen', False))


def resource_dir():
    """Folder holding templates/ and static/ (unpacked by PyInstaller when packaged)."""
    if frozen(): return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir():
    override = os.environ.get('UGW_DATA_DIR')
    if override: return Path(override)
    if frozen():
        base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
        return Path(base) / APP_NAME / 'data'
    return Path(__file__).resolve().parent.parent / 'data'


def database_path():
    return data_dir() / 'uganda_watch.sqlite3'
