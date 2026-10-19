; Per-user installation keeps the existing in-app updater writable.
; Build through tools/package_installers.py; no private workspace is harvested.
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef ApplicationId
  #define ApplicationId "{{09712A3B-9981-49CE-B0F5-6842497C799D}"
#endif

[Setup]
AppId={#ApplicationId}
AppName=Retro-Recomp
AppVersion={#AppVersion}
AppPublisher=Arthur Reboul Salze
AppPublisherURL=https://github.com/ArthurReboulSalze
AppSupportURL=https://github.com/ArthurReboulSalze/RetroRecomp/issues
AppUpdatesURL=https://github.com/ArthurReboulSalze/RetroRecomp/releases
DefaultDirName={localappdata}\Programs\Retro-Recomp
DefaultGroupName=Retro-Recomp
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Retro-Recomp-{#AppVersion}-windows-x64-setup
SetupIconFile={#PayloadDir}\Retro-Recomp.ico
UninstallDisplayIcon={app}\Retro-Recomp.exe
UninstallFilesDir={app}\uninstall
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile={#PayloadDir}\LICENSE.txt
InfoAfterFile={#PayloadDir}\INSTALL.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\Retro-Recomp.exe"; DestDir: "{app}"; Flags: restartreplace
Source: "{#PayloadDir}\LICENSE.txt"; DestDir: "{app}"
Source: "{#PayloadDir}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"
Source: "{#PayloadDir}\INSTALL.txt"; DestDir: "{app}"

[Icons]
Name: "{group}\Retro-Recomp"; Filename: "{app}\Retro-Recomp.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall Retro-Recomp"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Retro-Recomp"; Filename: "{app}\Retro-Recomp.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Retro-Recomp.exe"; Description: "{cm:LaunchProgram,Retro-Recomp}"; Flags: nowait postinstall skipifsilent

; No [UninstallDelete]: Games, datas, caches and all user-created files survive.
