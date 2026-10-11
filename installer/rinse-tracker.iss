; Inno Setup script for the Windows installer. Built by scripts/build_windows.ps1.
; Installs per-user (no admin rights needed). Your data is kept in %APPDATA%\Rinse Tracker,
; so uninstalling or upgrading the app never deletes your records.

[Setup]
AppName=Rinse Tracker
AppVersion=1.0.0
AppPublisher=Rinse Tracker
DefaultDirName={autopf}\Rinse Tracker
DefaultGroupName=Rinse Tracker
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Rinse-Tracker-Setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\Rinse Tracker.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Rinse Tracker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Rinse Tracker"; Filename: "{app}\Rinse Tracker.exe"
Name: "{autodesktop}\Rinse Tracker"; Filename: "{app}\Rinse Tracker.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Rinse Tracker.exe"; Description: "{cm:LaunchProgram,Rinse Tracker}"; Flags: nowait postinstall skipifsilent
