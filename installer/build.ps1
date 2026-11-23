# Build dist\installer\UgandaBusinessWatch-Setup-<version>.exe
# Needs: Python with requirements.txt + requirements-build.txt installed, and Inno Setup 6.
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
param([string]$Python = '', [string]$Iscc = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not $Python) {
    $Python = if (Test-Path -LiteralPath '.venv\Scripts\python.exe') { (Resolve-Path '.venv\Scripts\python.exe').Path } else { 'python' }
}
if (-not $Iscc) {
    $Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
              "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $Iscc) { throw 'Inno Setup 6 (ISCC.exe) was not found. Install it from https://jrsoftware.org/isinfo.php' }
}

$version = (& $Python -c "import ugwatch; print(ugwatch.__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) { throw 'Could not read the app version (ugwatch.__version__).' }
Write-Output "Building Uganda Business Watch $version"

# Windows file properties (Details tab) for the .exe.
$parts = ($version.Split('.') + @('0', '0', '0', '0'))[0..3] -join ', '
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($parts), prodvers=($parts)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Uganda Business Watch'),
    StringStruct('FileDescription', 'Uganda Business Watch'),
    StringStruct('FileVersion', '$version'),
    StringStruct('ProductName', 'Uganda Business Watch'),
    StringStruct('ProductVersion', '$version')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@ | Set-Content -LiteralPath 'installer\version.txt' -Encoding UTF8

& $Python installer\make_icon.py installer\app.ico
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $Python -m PyInstaller installer\UgandaBusinessWatch.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
& $Iscc "/DAppVersion=$version" installer\UgandaBusinessWatch.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed.' }
Get-ChildItem -LiteralPath 'dist\installer' -Filter '*.exe' | Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }
