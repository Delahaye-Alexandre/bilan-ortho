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
; L'app est un processus sans fenêtre : impossible de la fermer « proprement »
; via le gestionnaire de redémarrage → on force (et voir PrepareToInstall).
CloseApplications=force

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[InstallDelete]
; Mise a jour par-dessus une ancienne version : on purge le dossier _internal
; de PyInstaller AVANT la copie, sinon d'anciennes DLL residuelles cohabitent
; avec les nouvelles et provoquent des crashs au demarrage chez ceux qui
; mettent a jour (audit).
Type: filesandordirs; Name: "{app}\_internal"

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
; Mise à jour en un clic depuis l'application (app/maj.py) : installeur lancé
; en /SILENT avec /RELANCER=<port> — on relance l'app sur ce port, sans
; nouvelle fenêtre, la page ouverte se reconnecte seule (lanceur.py).
Filename: "{app}\BilanOrtho.exe"; Parameters: "--port={param:RELANCER|0} --sans-fenetre"; \
  Flags: nowait; Check: RelanceDemandee

; À la désinstallation, les données patient ({localappdata}\bilan-ortho :
; coffre chiffré + sauvegardes) sont volontairement PRÉSERVÉES.

[Code]
const
  { Version epinglee + empreinte SHA-256 officielle (GitHub Releases) :
    le telechargement est verifie avant d'etre execute en /VERYSILENT.
    A chaque montee de version : reprendre le digest de l'asset
    OllamaSetup.exe sur api.github.com/repos/ollama/ollama/releases. }
  OllamaVersion = '0.32.1';
  OllamaSHA256 = '2f53afab45547896e66b2879174ee78bb1f079f4a20b0858e0e377da0c3631f0';

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

function RelanceDemandee(): Boolean;
begin
  { /RELANCER=<port> n'est passé que par l'application elle-même. }
  Result := ExpandConstant('{param:RELANCER|0}') <> '0';
end;

procedure InitializeWizard;
begin
  OllamaOk := False;
  PageTelechargement := CreateDownloadPage(
    'Moteur d''IA local',
    'Téléchargement d''Ollama (~1 Go). Tout reste ensuite 100 % sur cet ordinateur.',
    nil);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  CodeSortie: Integer;
begin
  Result := '';
  { Une instance de l'app peut tourner en arrière-plan et verrouiller le
    dossier d'installation (processus sans fenêtre : le gestionnaire de
    redémarrage échoue à la fermer). On l'arrête avant la copie des
    fichiers ; sans instance, taskkill échoue silencieusement. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM BilanOrtho.exe', '',
    SW_HIDE, ewWaitUntilTerminated, CodeSortie);
  Sleep(500);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and (not OllamaPresent()) then begin
    PageTelechargement.Clear;
    PageTelechargement.Add(
      'https://github.com/ollama/ollama/releases/download/v' + OllamaVersion
        + '/OllamaSetup.exe',
      'OllamaSetup.exe', OllamaSHA256);
    PageTelechargement.Show;
    try
      try
        PageTelechargement.Download;
        OllamaOk := True;
      except
        { Hors ligne, lien indisponible ou empreinte SHA-256 non conforme :
          on n'interrompt pas l'installation — l'ecran « Premiere
          installation » de l'application prendra le relais. }
        Log('Téléchargement Ollama impossible : ' + GetExceptionMessage);
      end;
    finally
      PageTelechargement.Hide;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
var
  CodeSortie: Integer;
begin
  { L'app est un processus sans fenetre : on la force a quitter avant la
    desinstallation, sinon les fichiers verrouilles laissent une
    desinstallation partielle (audit). Sans instance, taskkill echoue
    silencieusement. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM BilanOrtho.exe', '',
    SW_HIDE, ewWaitUntilTerminated, CodeSortie);
  Sleep(500);
  Result := True;
end;
