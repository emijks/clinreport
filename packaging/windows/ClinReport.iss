; ClinReport for Windows — per-user installer (no administrator rights needed).
; Built by packaging/build.py --package:
;   ISCC /DAppVersion=3.0.0 /DAppVersionNumeric=3.0.0 /DOpenCravatVersion=… /DPythonVersion=…
;        /DSourceDir=<dist>\ClinReport /DOutputDir=<dist> /DOutputName=… ClinReport.iss
;
; Updating = running a newer installer over the old one (same AppId). Only {app}\python and {app}\modules are
; replaced wholesale; user data (settings, the lab's own templates, OpenCRAVAT jobs, logs) lives in
; %LOCALAPPDATA%\ClinReport and is never touched by install, update or uninstall (tests/packaging/test_installer.py).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric "0.0.0"
#endif
#ifndef OpenCravatVersion
  #define OpenCravatVersion "?"
#endif
#ifndef PythonVersion
  #define PythonVersion "?"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\ClinReport"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef OutputName
  #define OutputName "ClinReport-setup"
#endif

; Never change: it is what makes a new installer an update of the installed copy.
#define AppGuid "{6F0B7E3C-2C59-4C7B-9C5A-8E0F3B6C1A42}"
; Held by a running launcher (launchers/desktop/clinreport_desktop/instance.py, MUTEX_NAME).
#define LauncherMutex "ClinReportLauncher"
#define RepoUrl "https://github.com/emijks/clinreport"

[Setup]
AppId={{#AppGuid}
AppName=ClinReport
AppVersion={#AppVersion}
AppVerName=ClinReport {#AppVersion}
AppPublisher=GenLab
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
VersionInfoVersion={#AppVersionNumeric}
VersionInfoProductName=ClinReport
VersionInfoDescription=ClinReport {#AppVersion} setup
DefaultDirName={localappdata}\Programs\ClinReport
DefaultGroupName=ClinReport
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableWelcomePage=no
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile=clinreport.ico
UninstallDisplayIcon={app}\clinreport.ico
UninstallDisplayName=ClinReport
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardImageFile=wizard-large-164.bmp,wizard-large-246.bmp,wizard-large-328.bmp
WizardSmallImageFile=wizard-small-55.bmp,wizard-small-83.bmp,wizard-small-110.bmp
ShowLanguageDialog=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; PrepareToInstall stops ClinReport first; the Restart Manager is the safety net for anything else holding files.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.WelcomeUpdate=Будет выполнено обновление ClinReport %1 до версии %2.%n%nНастройки, свои шаблоны заключений и задания OpenCRAVAT сохранятся. Если ClinReport запущен, он будет закрыт автоматически.
english.WelcomeUpdate=ClinReport %1 will be updated to version %2.%n%nSettings, your own report templates and OpenCRAVAT jobs are kept. A running ClinReport is closed automatically.
russian.WelcomeInstall=Будет установлен ClinReport %1 — заключения по результатам OpenCRAVAT.%n%nВсё нужное входит в установку: OpenCRAVAT и Python отдельно ставить не надо. Права администратора не требуются.
english.WelcomeInstall=ClinReport %1 will be installed — clinical reports from OpenCRAVAT results.%n%nEverything it needs is included: no separate OpenCRAVAT or Python installation. No administrator rights required.
russian.MemoComponents=Компоненты:
english.MemoComponents=Components:
russian.MemoUpdate=Обновление: %1 → %2
english.MemoUpdate=Update: %1 → %2
russian.MemoUserData=Данные пользователя (сохраняются):
english.MemoUserData=User data (kept):
russian.StillRunning=Не удалось закрыть ClinReport. Закройте окно ClinReport и нажмите «Далее».
english.StillRunning=ClinReport could not be closed. Close the ClinReport window and click Next.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; A clean python/ and modules/ on every update: packages removed from the bundle must not linger.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\modules"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ClinReport"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; IconFilename: "{app}\clinreport.ico"
Name: "{userdesktop}\ClinReport"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; IconFilename: "{app}\clinreport.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,ClinReport}"; Flags: nowait postinstall skipifsilent
; In-app update (launchers/desktop/clinreport_desktop/updates.py): /SILENT /RELAUNCH=1 starts the new version.
Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; Flags: nowait; Check: RelaunchRequested

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\modules"

[Code]
function InstalledVersion(): String;
begin
  if not RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppGuid}_is1',
                             'DisplayVersion', Result) then
    Result := '';
end;

function RelaunchRequested(): Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;

procedure InitializeWizard();
var
  Previous: String;
begin
  Previous := InstalledVersion();
  if Previous <> '' then
    WizardForm.WelcomeLabel2.Caption := FmtMessage(CustomMessage('WelcomeUpdate'), [Previous, '{#AppVersion}'])
  else
    WizardForm.WelcomeLabel2.Caption := FmtMessage(CustomMessage('WelcomeInstall'), ['{#AppVersion}']);
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
var
  Previous: String;
begin
  Result := '';
  Previous := InstalledVersion();
  if Previous <> '' then
    Result := FmtMessage(CustomMessage('MemoUpdate'), [Previous, '{#AppVersion}']) + NewLine + NewLine;
  Result := Result + MemoDirInfo + NewLine + NewLine;
  Result := Result + CustomMessage('MemoComponents') + NewLine
    + Space + 'ClinReport {#AppVersion}' + NewLine
    + Space + 'OpenCRAVAT {#OpenCravatVersion}' + NewLine
    + Space + 'Python {#PythonVersion}' + NewLine + NewLine;
  Result := Result + CustomMessage('MemoUserData') + NewLine
    + Space + ExpandConstant('{localappdata}\ClinReport');
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

// Stop a running ClinReport before its files are replaced or removed, so Windows does not list its processes as
// "Python" applications on the "Preparing to Install" page:
// 1. the installed copy's own --quit (window, OpenCRAVAT server and its workers);
// 2. wait until the launcher's mutex is gone;
// 3. safety net — an older copy without --quit, or a hung process: end every process started from {app}.
function StopClinReport(): Boolean;
var
  ResultCode, I: Integer;
  AppDir, InstalledPython, Command: String;
begin
  AppDir := ExpandConstant('{app}');
  InstalledPython := AppDir + '\python\python.exe';
  if FileExists(InstalledPython) then
    Exec(InstalledPython, '-I -m clinreport_desktop --quit', AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);
  for I := 1 to 40 do
  begin
    if not CheckForMutexes('{#LauncherMutex}') then
      Break;
    Sleep(250);
  end;
  StringChangeEx(AppDir, '''', '''''', True);
  Command := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "Get-Process | Where-Object { $_.Path -and '
    + '$_.Path.StartsWith(''' + AppDir + '\'', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force"';
  Exec('powershell.exe', Command, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := not CheckForMutexes('{#LauncherMutex}');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not StopClinReport() then
    Result := CustomMessage('StillRunning');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopClinReport();
end;
