; MySolido Inno Setup Script
; Bouwt MySolido-Setup.exe — een Windows installer met wizard
; Downloadt en installeert Node.js en Python automatisch indien nodig

[Setup]
AppName=MySolido
AppVersion=1.0.0
AppVerName=MySolido 1.0.0
AppPublisher=MySolido
AppPublisherURL=https://mysolido.com
AppSupportURL=https://github.com/Wim1201/mysolido/issues
DefaultDirName=C:\MySolido
DefaultGroupName=MySolido
OutputDir=installer-output
OutputBaseFilename=MySolido-Setup
SetupIconFile=mysolido.ico
UninstallDisplayIcon={app}\mysolido.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[Messages]
dutch.WelcomeLabel1=Welkom bij MySolido
dutch.WelcomeLabel2=MySolido is jouw persoonlijke datakluis op je eigen pc.%n%nDeze wizard installeert alles wat nodig is:%n%n• MySolido applicatie%n• Node.js (indien nodig)%n• Python (indien nodig)%n• Alle afhankelijkheden%n%nDit kan 5-10 minuten duren.

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
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "start-mysolido.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "stop-mysolido.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\MySolido"; Filename: "{app}\start-mysolido.bat"; IconFilename: "{app}\mysolido.ico"; Comment: "Start MySolido — jouw persoonlijke datakluis"
Name: "{group}\MySolido Starten"; Filename: "{app}\start-mysolido.bat"; IconFilename: "{app}\mysolido.ico"
Name: "{group}\MySolido Stoppen"; Filename: "{app}\stop-mysolido.bat"
Name: "{group}\MySolido Verwijderen"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\start-mysolido.bat"; Description: "MySolido nu starten"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
Type: filesandordirs; Name: "{app}\node_modules"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\venv"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  NeedNode, NeedPython: Boolean;

// Check of een programma beschikbaar is via de command line
function ProgramInstalled(const ProgramName: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('cmd', '/c ' + ProgramName + ' --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function NodeInstalled: Boolean;
begin
  Result := ProgramInstalled('node');
end;

function PythonAvailable: Boolean;
begin
  Result := ProgramInstalled('python') or ProgramInstalled('python3');
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(
    'Benodigde software downloaden',
    'Even geduld — benodigde software wordt gedownload...',
    nil
  );
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;

  if CurPageID = wpReady then
  begin
    NeedNode := not NodeInstalled;
    NeedPython := not PythonAvailable;

    if NeedNode or NeedPython then
    begin
      DownloadPage.Clear;

      if NeedNode then
      begin
        DownloadPage.Add(
          'https://nodejs.org/dist/v20.18.1/node-v20.18.1-x64.msi',
          'node-installer.msi',
          ''
        );
      end;

      if NeedPython then
      begin
        DownloadPage.Add(
          'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe',
          'python-installer.exe',
          ''
        );
      end;

      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
        except
          if DownloadPage.AbortedByUser then
          begin
            Result := False;
            Exit;
          end
          else begin
            SuppressibleMsgBox(
              'Het downloaden van benodigde software is mislukt. ' +
              'Controleer je internetverbinding en probeer het opnieuw.',
              mbCriticalError, MB_OK, IDOK
            );
            Result := False;
            Exit;
          end;
        end;
      finally
        DownloadPage.Hide;
      end;

      // Node.js installeren (silent)
      if NeedNode then
      begin
        WizardForm.StatusLabel.Caption := 'Node.js installeren...';
        WizardForm.StatusLabel.Update;
        if not Exec(
          'msiexec',
          '/i "' + ExpandConstant('{tmp}\node-installer.msi') + '" /qn /norestart',
          '',
          SW_HIDE,
          ewWaitUntilTerminated,
          ResultCode
        ) then
        begin
          MsgBox('Node.js installatie mislukt. Installeer Node.js handmatig via https://nodejs.org', mbError, MB_OK);
        end;
      end;

      // Python installeren (silent, met PATH toevoeging)
      if NeedPython then
      begin
        WizardForm.StatusLabel.Caption := 'Python installeren...';
        WizardForm.StatusLabel.Update;
        if not Exec(
          ExpandConstant('{tmp}\python-installer.exe'),
          '/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1',
          '',
          SW_HIDE,
          ewWaitUntilTerminated,
          ResultCode
        ) then
        begin
          MsgBox('Python installatie mislukt. Installeer Python handmatig via https://python.org', mbError, MB_OK);
        end;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  AppDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    AppDir := ExpandConstant('{app}');

    // pip install
    WizardForm.StatusLabel.Caption := 'Python pakketten installeren...';
    WizardForm.StatusLabel.Update;
    Exec(
      'cmd',
      '/c pip install -r "' + AppDir + '\requirements.txt" --break-system-packages 2>nul || pip install -r "' + AppDir + '\requirements.txt"',
      AppDir,
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );

    // npm install
    WizardForm.StatusLabel.Caption := 'Community Solid Server installeren (dit kan even duren)...';
    WizardForm.StatusLabel.Update;
    Exec(
      'cmd',
      '/c npm install @solid/community-server',
      AppDir,
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;
end;
