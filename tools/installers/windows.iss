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
InfoBeforeFile={#PayloadDir}\RELEASE_NOTES.txt
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
; The base of paths of this release, read only like the copy the built-in update lays.
Source: "{#PayloadDir}\Retro-Recomp-base.zip"; DestDir: "{app}"; Attribs: readonly; Flags: overwritereadonly uninsremovereadonly
Source: "{#PayloadDir}\LICENSE.txt"; DestDir: "{app}"
Source: "{#PayloadDir}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"
Source: "{#PayloadDir}\INSTALL.txt"; DestDir: "{app}"
Source: "{#PayloadDir}\RELEASE_NOTES.txt"; DestDir: "{app}"

[Icons]
Name: "{group}\Retro-Recomp"; Filename: "{app}\Retro-Recomp.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall Retro-Recomp"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Retro-Recomp"; Filename: "{app}\Retro-Recomp.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Retro-Recomp.exe"; Description: "{cm:LaunchProgram,Retro-Recomp}"; Flags: nowait postinstall skipifsilent

; No [UninstallDelete]: Games, datas and all user-created files survive. The
; build tools and compiler caches installed beside the converter (datas/tools,
; .deps, .build) are removed only when the user answers yes to the question
; asked by the uninstaller, or passes /PURGETOOLS to a silent uninstall.

[CustomMessages]
english.PurgeToolsQuestion=Also remove the build tools and compiler caches (%1)?%n%nYour games, settings and discoveries are always kept.
english.PurgeToolsQuestionNoSize=Also remove the build tools and compiler caches?%n%nYour games, settings and discoveries are always kept.
english.PurgeToolsRemoving=Removing the build tools and compiler caches...
english.PurgeToolsMB=%1 MB
english.PurgeToolsGB=%1.%2 GB
french.PurgeToolsQuestion=Supprimer aussi les outils de compilation et les caches du compilateur (%1) ?%n%nTes jeux, tes réglages et tes découvertes sont toujours conservés.
french.PurgeToolsQuestionNoSize=Supprimer aussi les outils de compilation et les caches du compilateur ?%n%nTes jeux, tes réglages et tes découvertes sont toujours conservés.
french.PurgeToolsRemoving=Suppression des outils de compilation et des caches du compilateur...
french.PurgeToolsMB=%1 Mo
french.PurgeToolsGB=%1,%2 Go
german.PurgeToolsQuestion=Auch die Build-Werkzeuge und Compiler-Caches (%1) löschen?%n%nDeine Spiele, Einstellungen und Entdeckungen bleiben in jedem Fall erhalten.
german.PurgeToolsQuestionNoSize=Auch die Build-Werkzeuge und Compiler-Caches löschen?%n%nDeine Spiele, Einstellungen und Entdeckungen bleiben in jedem Fall erhalten.
german.PurgeToolsRemoving=Build-Werkzeuge und Compiler-Caches werden gelöscht...
german.PurgeToolsMB=%1 MB
german.PurgeToolsGB=%1,%2 GB
italian.PurgeToolsQuestion=Eliminare anche gli strumenti di compilazione e le cache del compilatore (%1)?%n%nGiochi, impostazioni e scoperte vengono sempre conservati.
italian.PurgeToolsQuestionNoSize=Eliminare anche gli strumenti di compilazione e le cache del compilatore?%n%nGiochi, impostazioni e scoperte vengono sempre conservati.
italian.PurgeToolsRemoving=Eliminazione degli strumenti di compilazione e delle cache del compilatore...
italian.PurgeToolsMB=%1 MB
italian.PurgeToolsGB=%1,%2 GB
spanish.PurgeToolsQuestion=¿Eliminar también las herramientas de compilación y las cachés del compilador (%1)?%n%nTus juegos, ajustes y descubrimientos se conservan siempre.
spanish.PurgeToolsQuestionNoSize=¿Eliminar también las herramientas de compilación y las cachés del compilador?%n%nTus juegos, ajustes y descubrimientos se conservan siempre.
spanish.PurgeToolsRemoving=Eliminando las herramientas de compilación y las cachés del compilador...
spanish.PurgeToolsMB=%1 MB
spanish.PurgeToolsGB=%1,%2 GB
russian.PurgeToolsQuestion=Удалить также инструменты сборки и кэши компилятора (%1)?%n%nВаши игры, настройки и находки сохраняются в любом случае.
russian.PurgeToolsQuestionNoSize=Удалить также инструменты сборки и кэши компилятора?%n%nВаши игры, настройки и находки сохраняются в любом случае.
russian.PurgeToolsRemoving=Удаление инструментов сборки и кэшей компилятора...
russian.PurgeToolsMB=%1 МБ
russian.PurgeToolsGB=%1,%2 ГБ

[Code]
// Optional removal of what the converter installed beside itself: the portable
// build tools (datas\tools), the engine sources and compiler builds (.deps) and
// the shared caches (.build). Only these three folders under {app}; a link or
// junction is never followed (one met inside is removed itself, one standing in
// place of a folder is left alone). Games, datas\* and everything else stay.
const
  AttrReadOnly = $1;
  AttrDirectory = $10;
  AttrNormal = $80;
  AttrReparsePoint = $400;
  MeasureLimit = 400000;    // entries counted before the size is left out

function DeleteFileW(Name: String): Boolean;
  external 'DeleteFileW@kernel32.dll stdcall';
function RemoveDirectoryW(Name: String): Boolean;
  external 'RemoveDirectoryW@kernel32.dll stdcall';
function SetFileAttributesW(Name: String; Attributes: LongWord): Boolean;
  external 'SetFileAttributesW@kernel32.dll stdcall';

// Paths beyond 260 characters (generated build trees) need the \\?\ form.
function LongPath(const Path: String): String;
begin
  if Copy(Path, 1, 4) = '\\?\' then
    Result := Path
  else if Copy(Path, 1, 2) = '\\' then
    Result := '\\?\UNC\' + Copy(Path, 3, Length(Path))
  else
    Result := '\\?\' + Path;
end;

function PurgeSwitchGiven: Boolean;
var
  Index: Integer;
begin
  Result := False;
  for Index := 1 to ParamCount do
    if CompareText(ParamStr(Index), '/PURGETOOLS') = 0 then
      Result := True;
end;

// Attributes of the entry itself (a link is not followed); -1 when absent.
function EntryAttributes(const Path: String): Integer;
var
  Find: TFindRec;
begin
  Result := -1;
  if FindFirst(LongPath(Path), Find) then
  begin
    Result := Find.Attributes;
    FindClose(Find);
  end;
end;

function IsRealFolder(const Path: String): Boolean;
var
  Attributes: Integer;
begin
  Attributes := EntryAttributes(Path);
  Result := (Attributes >= 0) and ((Attributes and AttrDirectory) <> 0)
    and ((Attributes and AttrReparsePoint) = 0);
end;

// The folder when it exists as a real folder all the way from {app}; else ''.
function ToolFolder(Index: Integer): String;
var
  App: String;
begin
  Result := '';
  App := RemoveBackslash(ExpandConstant('{app}'));
  case Index of
    0: if IsRealFolder(App + '\datas') and IsRealFolder(App + '\datas\tools') then Result := App + '\datas\tools';
    1: if IsRealFolder(App + '\.deps') then Result := App + '\.deps';
    2: if IsRealFolder(App + '\.build') then Result := App + '\.build';
  end;
end;

// Apparent size in bytes below Folder, links counted for nothing; -1 beyond
// MeasureLimit entries (the size is then not shown).
function FolderSize(const Folder: String; var Count: Integer): Int64;
var
  Find: TFindRec;
  Sub: Int64;
begin
  Result := 0;
  if FindFirst(LongPath(Folder) + '\*', Find) then
  begin
    try
      repeat
        if (Find.Name <> '.') and (Find.Name <> '..') and (Result >= 0) then
        begin
          Count := Count + 1;
          if Count > MeasureLimit then
            Result := -1
          else if (Find.Attributes and AttrReparsePoint) = 0 then
          begin
            if (Find.Attributes and AttrDirectory) <> 0 then
            begin
              Sub := FolderSize(Folder + '\' + Find.Name, Count);
              if Sub < 0 then
                Result := -1
              else
                Result := Result + Sub;
            end
            else
              Result := Result + Int64(Find.SizeHigh) * 4294967296 + Int64(Find.SizeLow);
          end;
        end;
      until (Result < 0) or (not FindNext(Find));
    finally
      FindClose(Find);
    end;
  end;
end;

function SizeText(Bytes: Int64): String;
var
  Megabytes, Tenths: Int64;
begin
  Megabytes := (Bytes + 1048575) div 1048576;
  if Megabytes < 1024 then
    Result := FmtMessage(CustomMessage('PurgeToolsMB'), [IntToStr(Megabytes)])
  else
  begin
    Tenths := (Megabytes * 10 + 512) div 1024;
    Result := FmtMessage(CustomMessage('PurgeToolsGB'), [IntToStr(Tenths div 10), IntToStr(Tenths mod 10)]);
  end;
end;

// Removes the folder and everything in it. A link or junction is removed
// itself, never entered. Read-only files (Git checkouts) are made writable.
function RemoveTree(const Folder: String): Boolean;
var
  Find: TFindRec;
  Child: String;
begin
  Result := True;
  if FindFirst(LongPath(Folder) + '\*', Find) then
  begin
    try
      repeat
        if (Find.Name <> '.') and (Find.Name <> '..') then
        begin
          Child := Folder + '\' + Find.Name;
          if (Find.Attributes and AttrReparsePoint) <> 0 then
          begin
            if (Find.Attributes and AttrDirectory) <> 0 then
            begin
              if not RemoveDirectoryW(LongPath(Child)) then Result := False;
            end
            else if not DeleteFileW(LongPath(Child)) then Result := False;
          end
          else if (Find.Attributes and AttrDirectory) <> 0 then
          begin
            if not RemoveTree(Child) then Result := False;
          end
          else
          begin
            if (Find.Attributes and AttrReadOnly) <> 0 then
              SetFileAttributesW(LongPath(Child), AttrNormal);
            if not DeleteFileW(LongPath(Child)) then Result := False;
          end;
        end;
      until not FindNext(Find);
    finally
      FindClose(Find);
    end;
  end;
  if not RemoveDirectoryW(LongPath(Folder)) then Result := False;
end;

procedure PurgeTools(const Folders: array of String);
var
  Index: Integer;
  App: String;
begin
  UninstallProgressForm.StatusLabel.Caption := CustomMessage('PurgeToolsRemoving');
  for Index := 0 to GetArrayLength(Folders) - 1 do
    if Folders[Index] <> '' then
      RemoveTree(Folders[Index]);
  // An empty datas folder is not worth keeping; one with settings stays.
  App := RemoveBackslash(ExpandConstant('{app}'));
  if IsRealFolder(App + '\datas') then
    RemoveDir(App + '\datas');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Folders: array of String;
  Index, Count, Found: Integer;
  Total, Size: Int64;
  Purge: Boolean;
  Question: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  SetArrayLength(Folders, 3);
  Found := 0;
  for Index := 0 to 2 do
  begin
    Folders[Index] := ToolFolder(Index);
    if Folders[Index] <> '' then
      Found := Found + 1;
  end;
  if Found = 0 then
    Exit;
  // A silent uninstall keeps them unless /PURGETOOLS is given.
  Purge := PurgeSwitchGiven;
  if (not Purge) and (not UninstallSilent) then
  begin
    Total := 0;
    Count := 0;
    for Index := 0 to 2 do
      if (Folders[Index] <> '') and (Total >= 0) then
      begin
        Size := FolderSize(Folders[Index], Count);
        if Size < 0 then
          Total := -1
        else
          Total := Total + Size;
      end;
    if Total >= 0 then
      Question := FmtMessage(CustomMessage('PurgeToolsQuestion'), [SizeText(Total)])
    else
      Question := CustomMessage('PurgeToolsQuestionNoSize');
    Purge := SuppressibleMsgBox(Question, mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
  end;
  if Purge then
    PurgeTools(Folders);
end;
