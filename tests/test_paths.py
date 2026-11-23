"""Where data and app files live: project folder, installed .exe, or UGW_DATA_DIR."""
import sys
from pathlib import Path

from ugwatch import paths


def test_project_folder_keeps_data_in_data(monkeypatch):
    monkeypatch.delenv('UGW_DATA_DIR', raising=False)
    monkeypatch.delattr(sys, 'frozen', raising=False)
    root = Path(paths.__file__).resolve().parent.parent
    assert paths.data_dir() == root / 'data' and paths.resource_dir() == root
    assert paths.database_path() == root / 'data' / 'uganda_watch.sqlite3'


def test_installed_app_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.delenv('UGW_DATA_DIR', raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path / 'bundle'), raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))
    assert paths.frozen()
    assert paths.data_dir() == tmp_path / 'Local' / 'UgandaBusinessWatch' / 'data'
    assert paths.resource_dir() == tmp_path / 'bundle'


def test_data_folder_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv('UGW_DATA_DIR', str(tmp_path / 'usb'))
    assert paths.data_dir() == tmp_path / 'usb'
