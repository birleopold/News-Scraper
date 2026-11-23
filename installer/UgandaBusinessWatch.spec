# PyInstaller recipe for UgandaBusinessWatch.exe. Build with installer/build.ps1.
# A folder build (not one file): it starts faster and antivirus tools flag it less often.
from PyInstaller.utils.hooks import collect_data_files

root = SPECPATH + '/..'

a = Analysis(
    [root + '/run.py'],
    pathex=[root],
    datas=[(root + '/templates', 'templates'), (root + '/static', 'static')]
          + collect_data_files('tzdata'),          # Africa/Kampala time zone on Windows
    hiddenimports=['ugwatch.ocr', 'ugwatch.ics'],
    excludes=['tkinter', 'pytest'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='UgandaBusinessWatch',
    icon=root + '/installer/app.ico',
    console=False,                                 # runs in the background; logs go to data/app.log
    version=root + '/installer/version.txt',
)
coll = COLLECT(exe, a.binaries, a.datas, name='UgandaBusinessWatch')
