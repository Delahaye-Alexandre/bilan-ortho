; Installeur Windows de Bilan Ortho (Inno Setup 6).
; Compilé par la CI : ISCC.exe /DAppVersion=x.y.z installeur.iss
; Installation PAR UTILISATEUR (aucun droit administrateur requis).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7E1F4C2A-9B7D-4A53-8F21-0B11A407C901}
AppName=Bilan Ortho
AppVersion={#AppVersion}
AppPublisher=Alexandre Delahaye
DefaultDirName={localappdata}\Programs\BilanOrtho
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=Output
OutputBaseFilename=BilanOrtho-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\BilanOrtho.exe

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\..\dist\BilanOrtho\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userdesktop}\Bilan Ortho"; Filename: "{app}\BilanOrtho.exe"
Name: "{userprograms}\Bilan Ortho"; Filename: "{app}\BilanOrtho.exe"

[Run]
; Ollama : installé silencieusement s'il vient d'être téléchargé (voir [Code]).
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; \
  StatusMsg: "Installation du moteur d'IA local (Ollama)…"; \
  Check: OllamaTelecharge; Flags: waituntilterminated
; Démarre Ollama (icône près de l'horloge) pour que le premier lancement le trouve.
Filename: "{localappdata}\Programs\Ollama\ollama app.exe"; \
  Flags: nowait skipifdoesntexist
Filename: "{app}\BilanOrtho.exe"; Description: "Lancer Bilan Ortho"; Flags: postinstall nowait skipifsilent

; À la désinstallation, les données patient ({localappdata}\bilan-ortho :
; coffre chiffré + sauvegardes) sont volontairement PRÉSERVÉES.

[Code]
var
  PageTelechargement: TDownloadWizardPage;
  OllamaOk: Boolean;

function OllamaPresent(): Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
    or FileExists(ExpandConstant('{pf}\Ollama\ollama.exe'));
end;

function OllamaTelecharge(): Boolean;
begin
  Result := OllamaOk and FileExists(ExpandConstant('{tmp}\OllamaSetup.exe'));
end;

procedure InitializeWizard;
begin
  OllamaOk := False;
  PageTelechargement := CreateDownloadPage(
    'Moteur d''IA local',
    'Téléchargement d''Ollama (~1 Go). Tout reste ensuite 100 % sur cet ordinateur.',
    nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and (not OllamaPresent()) then begin
    PageTelechargement.Clear;
    PageTelechargement.Add('https://ollama.com/download/OllamaSetup.exe', 'OllamaSetup.exe', '');
    PageTelechargement.Show;
    try
      try
        PageTelechargement.Download;
        OllamaOk := True;
      except
        { Hors ligne ou lien indisponible : on n'interrompt pas l'installation —
          l'écran « Première installation » de l'application guidera l'utilisatrice. }
        Log('Téléchargement Ollama impossible : ' + GetExceptionMessage);
      end;
    finally
      PageTelechargement.Hide;
    end;
  end;
end;
