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
Filename: "{app}\BilanOrtho.exe"; Description: "Lancer Bilan Ortho"; Flags: postinstall nowait skipifsilent

; À la désinstallation, les données patient ({localappdata}\bilan-ortho :
; coffre chiffré + sauvegardes) sont volontairement PRÉSERVÉES.
