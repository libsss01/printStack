[Setup]
AppName=PrintStack
AppVersion=1.0.0
DefaultDirName={pf}\PrintStack
DefaultGroupName=PrintStack
OutputDir=.\Output
OutputBaseFilename=setup_printstack
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Icônes supplémentaires:"; Flags: unchecked
Name: "startupicon"; Description: "Lancer l'application automatiquement au démarrage de Windows"; GroupDescription: "Démarrage automatique:"

[Files]
Source: "dist\PrintStack\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PrintStack"; Filename: "{app}\PrintStack.exe"
Name: "{group}\Désinstaller PrintStack"; Filename: "{uninstallexe}"
Name: "{commondesktop}\PrintStack"; Filename: "{app}\PrintStack.exe"; Tasks: desktopicon
; Ceci place un raccourci dans le dossier "Démarrage" pour tous les utilisateurs
Name: "{commonstartup}\PrintStack"; Filename: "{app}\PrintStack.exe"; Tasks: startupicon

[Run]
Filename: "{app}\PrintStack.exe"; Description: "Lancer PrintStack"; Flags: nowait postinstall skipifsilent
