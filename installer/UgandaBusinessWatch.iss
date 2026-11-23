; Inno Setup script for UgandaBusinessWatch-Setup.exe. Build with installer\build.ps1.
; Per-user install (no administrator rights). Your data lives in
; %LOCALAPPDATA%\UgandaBusinessWatch\data and is kept when you uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Uganda Business Watch"
#define AppExe "UgandaBusinessWatch.exe"

[Setup]
AppId={{6B1E7F2A-3C59-4D7E-9A41-2F8C5B0D7E31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Uganda Business Watch
AppComments=Tenders, disposals of public assets, auctions and jobs in Uganda, in one local dashboard.
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=UgandaBusinessWatch-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Close a running copy before replacing its files (upgrades) and never restart it half-way.
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Messages]
FinishedLabel=Setup has installed [name]. It runs in the background and opens in your web browser at http://127.0.0.1:5050.%n%nYour data is kept in %LOCALAPPDATA%\UgandaBusinessWatch\data.

[Tasks]
Name: "autostart"; Description: "Start automatically when I sign in to Windows (recommended)"; GroupDescription: "Background:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\UgandaBusinessWatch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Open your opportunity desk"
Name: "{autoprograms}\{#AppName} (data folder)"; Filename: "{localappdata}\UgandaBusinessWatch\data"; Comment: "Database, backups and log"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Start quietly at sign-in (no browser window); remove the entry on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "UgandaBusinessWatch"; \
  ValueData: """{app}\{#AppExe}"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopApp"

[Code]
procedure StopRunningCopy();
var
  Code: Integer;
begin
  { The app runs in the background with no window; stop it so its files can be replaced. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningCopy();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { Unticking "start automatically" on an upgrade must also remove the old sign-in entry. }
  if (CurStep = ssPostInstall) and (not WizardIsTaskSelected('autostart')) then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'UgandaBusinessWatch');
end;
