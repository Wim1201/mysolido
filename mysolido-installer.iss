; MySolido Inno Setup Script
; Bouwt MySolido-Setup.exe — een Windows installer met wizard

[Setup]
AppName=MySolido
AppVersion=0.9.0
AppPublisher=MySolido
AppPublisherURL=https://mysolido.com
AppSupportURL=https://github.com/Wim1201/mysolido
DefaultDirName={autopf}\MySolido
DefaultGroupName=MySolido
OutputDir=installer-output
OutputBaseFilename=MySolido-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
SetupIconFile=mysolido.ico
UninstallDisplayIcon={app}\mysolido.ico
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[Files]
; MySolido bronbestanden
Source: "app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "share_links.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "shares.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "audit.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "trash.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "notifications.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "sync_bridge.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "package.json"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "mysolido.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs
Source: "static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs

; Start/stop scripts
Source: "start-mysolido.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "stop-mysolido.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MySolido Starten"; Filename: "{app}\start-mysolido.bat"; IconFilename: "{app}\mysolido.ico"; Comment: "Start MySolido"
Name: "{group}\MySolido Stoppen"; Filename: "{app}\stop-mysolido.bat"; Comment: "Stop MySolido"
Name: "{group}\MySolido Verwijderen"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MySolido"; Filename: "{app}\start-mysolido.bat"; IconFilename: "{app}\mysolido.ico"; Comment: "Start MySolido"

[Run]
; Na installatie: pip install en npm install
Filename: "pip"; Parameters: "install -r ""{app}\requirements.txt"""; StatusMsg: "Python dependencies installeren..."; Flags: runhidden waituntilterminated
Filename: "npm"; Parameters: "install @solid/community-server"; WorkingDir: "{app}"; StatusMsg: "Community Solid Server installeren..."; Flags: runhidden waituntilterminated
; Optioneel: MySolido direct starten na installatie
Filename: "{app}\start-mysolido.bat"; Description: "MySolido nu starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\node_modules"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function NodeJsInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('node', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PythonInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
var
  ErrMsg: String;
begin
  Result := True;
  ErrMsg := '';

  if not NodeJsInstalled() then
    ErrMsg := ErrMsg + '• Node.js is niet gevonden. Download het van https://nodejs.org' + #13#10;

  if not PythonInstalled() then
    ErrMsg := ErrMsg + '• Python is niet gevonden. Download het van https://python.org' + #13#10;

  if ErrMsg <> '' then
  begin
    if MsgBox('De volgende vereisten ontbreken:' + #13#10#13#10 + ErrMsg + #13#10 +
              'Installeer deze eerst en probeer het opnieuw.' + #13#10#13#10 +
              'Toch doorgaan? (niet aanbevolen)', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
