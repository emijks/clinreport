; ClinReport for Windows — per-user installer (no administrator rights needed).
; Built by packaging/build.py --package:
;   ISCC /DAppVersion=3.0.0 /DAppVersionNumeric=3.0.0 /DSourceDir=<dist>\ClinReport /DOutputDir=<dist> /DOutputName=… ClinReport.iss
; User data (settings, templates, jobs, logs) lives in %LOCALAPPDATA%\ClinReport and is kept on uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric "0.0.0"
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

[Setup]
AppId={{6F0B7E3C-2C59-4C7B-9C5A-8E0F3B6C1A42}
AppName=ClinReport
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersionNumeric}
AppPublisher=GenLab
AppPublisherURL=https://github.com/emijks/clinreport
DefaultDirName={localappdata}\Programs\ClinReport
DefaultGroupName=ClinReport
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile=clinreport.ico
UninstallDisplayIcon={app}\clinreport.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Files of a running ClinReport (python.exe, OpenCRAVAT) are closed through the Restart Manager.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; A clean python/ on every update: packages removed from the bundle must not linger.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\modules"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ClinReport"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; IconFilename: "{app}\clinreport.ico"
Name: "{userdesktop}\ClinReport"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; IconFilename: "{app}\clinreport.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m clinreport_desktop"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,ClinReport}"; Flags: nowait postinstall skipifsilent

[Code]
// Before the files-in-use check: stop a running ClinReport cleanly with the installed copy's own --quit
// (window, OpenCRAVAT server and its Celery workers), so Windows does not list them as "Python" applications.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  InstalledPython: String;
begin
  Result := '';
  InstalledPython := ExpandConstant('{app}\python\python.exe');
  if FileExists(InstalledPython) then
    Exec(InstalledPython, '-I -m clinreport_desktop --quit', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

[UninstallRun]
; Stop a running ClinReport and its OpenCRAVAT server before files are removed.
Filename: "{app}\python\python.exe"; Parameters: "-I -m clinreport_desktop --quit"; Flags: runhidden waituntilterminated; RunOnceId: "StopClinReport"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\modules"
