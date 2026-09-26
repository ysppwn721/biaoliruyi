; Windows installer definition for Inno Setup 6.
; The portable ZIP remains available for users who do not want an installer.
[Setup]
AppId={{A4E2E8C1-6A57-4F9D-BB2B-4C7A9F1E2D11}
AppName=知链
AppVersion=0.2.1
AppPublisher=知链项目组
AppPublisherURL=https://zhilian.space/
AppSupportURL=https://zhilian.space/
DefaultDirName={localappdata}\Programs\Zhilian
DefaultGroupName=知链
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
OutputDir=..\artifacts
OutputBaseFilename=Zhilian-0.2.1-windows-x64-setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=知链 0.2.1
; Keep user projects and exports under %LOCALAPPDATA%\Zhilian after uninstall.
Uninstallable=yes

[Files]
Source: "..\dist\Zhilian\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Icons]
Name: "{group}\知链"; Filename: "{app}\Zhilian.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\知链"; Filename: "{app}\Zhilian.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Zhilian.exe"; Description: "启动知链"; Flags: nowait postinstall skipifsilent
