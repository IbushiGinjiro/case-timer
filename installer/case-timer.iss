; case-timer のインストーラー（Inno Setup 6）。build.py から ISCC で作る
#define AppName "case-timer"
#define AppVersion "1.0.0"
#define AppExe "case-timer.exe"

[Setup]
AppId={{6C1E3A52-8F0B-4D3E-9A57-C4E2B7D1F0A9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=IbushiGinjiro
AppPublisherURL=https://github.com/IbushiGinjiro/case-timer
; ユーザーごとのインストール（管理者権限は不要）。%LOCALAPPDATA%\Programs\case-timer に入る
PrivilegesRequired=lowest
DefaultDirName={userpf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\release
OutputBaseFilename=case-timer-setup-{#AppVersion}
SetupIconFile=..\assets\case-timer.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 起動中なら閉じるよう案内する（上書きインストール・アンインストール時）
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "autostart"; Description: "PCの起動時に自動で立ち上げる"
Name: "desktopicon"; Description: "デスクトップにショートカットを作る"; Flags: unchecked

[Files]
Source: "..\dist\case-timer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; アプリの設定画面の「PCの起動時に自動で立ち上げる」と同じ登録先（app/autostart.py）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "case-timer"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "case-timer を起動する"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; アンインストール前にアプリを閉じる
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
// アプリの設定画面から自動起動をオンにした場合（インストール時に選ばなかった場合）も、登録を消す
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'case-timer');
end;
