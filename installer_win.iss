; ──────────────────────────────────────────────────────────────────────
; Inno Setup script for PassLock Windows installer.
;
; Download Inno Setup: https://jrsoftware.org/isinfo.php
; Compile this file with Inno Setup after running build.bat.
; ──────────────────────────────────────────────────────────────────────

[Setup]
AppName=PassLock
AppVersion=1.0.0
AppPublisher=PassLock Contributors
DefaultDirName={autopf}\PassLock
DefaultGroupName=PassLock
OutputDir=installer
OutputBaseFilename=PassLock-Setup-1.0.0-Windows
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Files]
Source: "dist\PassLock.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PassLock"; Filename: "{app}\PassLock.exe"
Name: "{autodesktop}\PassLock"; Filename: "{app}\PassLock.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\PassLock.exe"; Description: "Launch PassLock"; Flags: nowait postinstall skipifsilent
