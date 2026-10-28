#ifndef AppVersion
  #error AppVersion must be supplied by build.ps1
#endif

[Setup]
AppId={{A13D9204-47CB-44C7-B2AB-3EA5F31280B1}
AppName=EduTrack Desktop
AppVersion={#AppVersion}
AppPublisher=EduTrack
DefaultDirName={localappdata}\Programs\EduTrack Desktop
DefaultGroupName=EduTrack Desktop
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=dist\installer
OutputBaseFilename=EduTrackDesktop-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=EduTrack Desktop
UninstallDisplayIcon={app}\EduTrackDesktop.exe

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\EduTrackDesktop.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\EduTrack Desktop"; Filename: "{app}\EduTrackDesktop.exe"
Name: "{autodesktop}\EduTrack Desktop"; Filename: "{app}\EduTrackDesktop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EduTrackDesktop.exe"; Description: "Iniciar EduTrack Desktop"; Flags: postinstall nowait skipifsilent
