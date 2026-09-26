; Optional Windows installer definition for Inno Setup 6.
; The portable ZIP remains the primary no-admin distribution.
[Setup]
AppId={{A4E2E8C1-6A57-4F9D-BB2B-4C7A9F1E2D11}
AppName=知链
AppVersion=0.2.1
DefaultDirName={autopf}\Zhilian
DefaultGroupName=知链
OutputDir=..\artifacts
OutputBaseFilename=Zhilian-0.2.1-windows-x64-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Files]
Source: "..\dist\Zhilian\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\知链"; Filename: "{app}\Zhilian.exe"
Name: "{autodesktop}\知链"; Filename: "{app}\Zhilian.exe"

[Run]
Filename: "{app}\Zhilian.exe"; Description: "启动知链"; Flags: nowait postinstall skipifsilent
