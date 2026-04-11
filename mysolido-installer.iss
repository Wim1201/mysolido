; MySolido Inno Setup Script — Portable Edition
; Bouwt MySolido-Setup.exe — installeert Node.js en Python LOKAAL (geen admin nodig)
; Downloads: Node.js portable zip + Python embeddable zip + get-pip.py

[Setup]
AppName=MySolido
AppVersion=1.3.0
AppVerName=MySolido 1.3.0
AppPublisher=MySolido
AppPublisherURL=https://mysolido.com
AppSupportURL=https://github.com/Wim1201/mysolido/issues
DefaultDirName={localappdata}\MySolido
DefaultGroupName=MySolido
OutputDir=installer-output
OutputBaseFilename=MySolido-Setup
SetupIconFile=mysolido.ico
UninstallDisplayIcon={app}\mysolido.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
; GEEN admin-rechten nodig!
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[Messages]
dutch.WelcomeLabel1=Welkom bij MySolido
dutch.WelcomeLabel2=MySolido is jouw persoonlijke datakluis op je eigen pc.%n%nDeze wizard installeert alles wat nodig is. Er zijn geen admin-rechten nodig.%n%nDit kan 5-10 minuten duren bij de eerste keer.

[Files]
; MySolido bronbestanden
Source: "app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "share_links.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "shares.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "audit.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "trash.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "notifications.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "sync_bridge.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "watermark.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "translations.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "ai_service.py"; DestDir: "{app}"; Flags: ignoreversion
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
Type: filesandordirs; Name: "{app}\node"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\node_modules"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  NeedNode, NeedPython: Boolean;

function NodeExistsLocally: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\node\node.exe'));
end;

function PythonExistsLocally: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\python\python.exe'));
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(
    'Benodigde software downloaden',
    'Even geduld — Node.js en Python worden gedownload...',
    nil
  );
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = wpReady then
  begin
    NeedNode := not NodeExistsLocally;
    NeedPython := not PythonExistsLocally;

    if NeedNode or NeedPython then
    begin
      DownloadPage.Clear;

      if NeedNode then
      begin
        DownloadPage.Add(
          'https://nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip',
          'node-portable.zip',
          ''
        );
      end;

      if NeedPython then
      begin
        DownloadPage.Add(
          'https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip',
          'python-portable.zip',
          ''
        );
        // get-pip.py voor pip installatie
        DownloadPage.Add(
          'https://bootstrap.pypa.io/get-pip.py',
          'get-pip.py',
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
              'Het downloaden is mislukt. Controleer je internetverbinding en probeer het opnieuw.',
              mbCriticalError, MB_OK, IDOK
            );
            Result := False;
            Exit;
          end;
        end;
      finally
        DownloadPage.Hide;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  AppDir, NodeDir, PythonDir, NodeZip, PythonZip, GetPipPath: String;
  PthFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    AppDir := ExpandConstant('{app}');
    NodeDir := AppDir + '\node';
    PythonDir := AppDir + '\python';
    NodeZip := ExpandConstant('{tmp}\node-portable.zip');
    PythonZip := ExpandConstant('{tmp}\python-portable.zip');
    GetPipPath := ExpandConstant('{tmp}\get-pip.py');

    // Node.js uitpakken
    if NeedNode and FileExists(NodeZip) then
    begin
      WizardForm.StatusLabel.Caption := 'Node.js uitpakken...';
      WizardForm.StatusLabel.Update;
      ForceDirectories(NodeDir);
      // Uitpakken met PowerShell, daarna submappen platslaan
      Exec(
        'powershell',
        '-NoProfile -Command "Expand-Archive -Path ''' + NodeZip + ''' -DestinationPath ''' + NodeDir + ''' -Force; ' +
        'Get-ChildItem ''' + NodeDir + ''' -Directory | Where-Object { $_.Name -like ''node-*'' } | ForEach-Object { ' +
        'Get-ChildItem $_.FullName | Move-Item -Destination ''' + NodeDir + ''' -Force; ' +
        'Remove-Item $_.FullName -Force -Recurse }"',
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode
      );
    end;

    // Python uitpakken
    if NeedPython and FileExists(PythonZip) then
    begin
      WizardForm.StatusLabel.Caption := 'Python uitpakken...';
      WizardForm.StatusLabel.Update;
      ForceDirectories(PythonDir);
      Exec(
        'powershell',
        '-NoProfile -Command "Expand-Archive -Path ''' + PythonZip + ''' -DestinationPath ''' + PythonDir + ''' -Force"',
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode
      );

      // Python embeddable heeft een ._pth bestand dat import beperkt
      // Pas het aan zodat pip en site-packages werken
      PthFile := PythonDir + '\python312._pth';
      if FileExists(PthFile) then
      begin
        SaveStringToFile(PthFile,
          'python312.zip' + #13#10 +
          '.' + #13#10 +
          'Lib' + #13#10 +
          'Lib\site-packages' + #13#10 +
          'import site' + #13#10 +
          AppDir + #13#10,
          False
        );
      end;

      // Installeer pip via get-pip.py
      if FileExists(GetPipPath) then
      begin
        WizardForm.StatusLabel.Caption := 'pip installeren...';
        WizardForm.StatusLabel.Update;
        CopyFile(GetPipPath, PythonDir + '\get-pip.py', False);
        Exec(
          PythonDir + '\python.exe',
          'get-pip.py --no-warn-script-location',
          PythonDir,
          SW_HIDE,
          ewWaitUntilTerminated,
          ResultCode
        );
      end;
    end;

    // pip install requirements
    WizardForm.StatusLabel.Caption := 'Python pakketten installeren...';
    WizardForm.StatusLabel.Update;
    Exec(
      PythonDir + '\python.exe',
      '-m pip install -r "' + AppDir + '\requirements.txt" --no-warn-script-location',
      AppDir,
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );

    // npm install community-solid-server
    WizardForm.StatusLabel.Caption := 'Community Solid Server installeren (even geduld)...';
    WizardForm.StatusLabel.Update;
    Exec(
      NodeDir + '\npm.cmd',
      'install @solid/community-server',
      AppDir,
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;
end;
