; Inno Setup 6 — MarkItDown GUI Windows x64 安装包
; 由 scripts\build-windows-setup.cmd 调用；版本号用 /DMyAppVersion=... 传入。

#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif

#define MyAppName "MarkItDown GUI"
#define MyAppPublisher "NACXA0"
#define MyAppExeName "markitdown-gui.exe"

[Setup]
; 固定 AppId，覆盖升级时识别为同一应用
AppId={{E8F3C2A1-9B47-4D6E-A5F1-2C8D0E7B4A19}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/NACXA0/markitdown-gui
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\windows
OutputBaseFilename=MarkItDown_GUI-{#MyAppVersion}-x64-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 整个 flet build windows 目录（exe、插件 DLL、data、随包 pandoc）
Source: "..\build\windows\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
