; Inno Setup script for the Trading Journal Windows installer. Built by scripts/build_journal_windows.ps1.
; Installs per-user (no admin rights needed). Your data is kept in %APPDATA%\Trading Journal,
; so uninstalling or upgrading the app never deletes your records.

[Setup]
AppName=Trading Journal
AppVersion=0.1.0
AppPublisher=Trading Journal
DefaultDirName={autopf}\Trading Journal
DefaultGroupName=Trading Journal
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Trading-Journal-Setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\Trading Journal.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Trading Journal\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Trading Journal"; Filename: "{app}\Trading Journal.exe"
Name: "{autodesktop}\Trading Journal"; Filename: "{app}\Trading Journal.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Trading Journal.exe"; Description: "{cm:LaunchProgram,Trading Journal}"; Flags: nowait postinstall skipifsilent
