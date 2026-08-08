#define AppName "ArchivAgent"
#define AppVersion "6.0.0 RC9"
#define AppExe "ArchivAgent.exe"
#define ModelId "a0daddf4-4a50-502d-91d7-8f72e8577a33"

[Setup]
AppId={{ECDB1195-FE8F-4D89-97B3-AF86A272991A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Frank Bernbeck
AppPublisherURL=https://archivagent.com
DefaultDirName=C:\ArchivAgent
DefaultGroupName=ArchivAgent
PrivilegesRequired=admin
OutputDir=..\output
OutputBaseFilename=ArchivAgent_Setup_6.0.0_RC9
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\docs\LIZENZHINWEISE.txt
InfoBeforeFile=..\docs\VOR_DER_INSTALLATION.txt

[Languages]
Name: german; MessagesFile: "compiler:Languages\German.isl"
Name: english; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: desktopicon; Description: "Desktop-Verknüpfung erstellen"; Flags: unchecked

[Files]
Source: "..\stage\ArchivAgent\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{app}\Projekte"; Permissions: users-modify
Name: "{app}\Logs"; Permissions: users-modify

[Icons]
Name: "{group}\ArchivAgent"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\ArchivAgent – OCR-Assistent"; Filename: "{app}\OCR_Assistent\ArchivAgent_OCR_Assistent.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ArchivAgent"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\OCR_Assistent\ArchivAgent_OCR_Assistent.exe"; Description: "OCR-Assistent öffnen"; Flags: postinstall nowait skipifsilent; Check: NeedsOcrSetup
Filename: "{app}\{#AppExe}"; Description: "ArchivAgent starten"; Flags: postinstall nowait skipifsilent

[Code]
function NeedsOcrSetup(): Boolean;
begin
  Result := not FileExists(ExpandConstant('{app}\runtime\Scripts\kraken.exe'));
end;
