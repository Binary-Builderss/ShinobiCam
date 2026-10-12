; Inno Setup 6 - installer per utente (niente diritti di amministratore).
; Compilato da scripts\build.ps1 dopo PyInstaller:  ISCC /DMyAppVersion=1.0.0 installer\ShinobiCam.iss
; Output: dist\ShinobiCam-<versione>-setup.exe

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
; AppId identifica l'app per aggiornamenti e disinstallazione: non cambiarlo mai.
AppId={{6E1B7C52-3A9D-4F08-B6C1-8D2E5A4F9B37}
AppName=ShinobiCam
AppVersion={#MyAppVersion}
AppVerName=ShinobiCam {#MyAppVersion}
AppPublisher=Binary Builders
DefaultDirName={autopf}\ShinobiCam
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=ShinobiCam-{#MyAppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\ShinobiCam.exe
UninstallDisplayName=ShinobiCam
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Chiude ShinobiCam in esecuzione prima di aggiornare o disinstallare (Restart Manager).
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Un aggiornamento non deve mescolare librerie della versione precedente con quelle nuove.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ShinobiCam\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ShinobiCam"; Filename: "{app}\ShinobiCam.exe"
Name: "{autodesktop}\ShinobiCam"; Filename: "{app}\ShinobiCam.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ShinobiCam.exe"; Description: "{cm:LaunchProgram,ShinobiCam}"; Flags: nowait postinstall skipifsilent

; I dati utente (%APPDATA%\ShinobiCam: impostazioni, sigillo, sfondo, log) restano dopo la
; disinstallazione, così una reinstallazione non obbliga a ricalibrare.

[Code]
const
  ObsVirtualCamClsid = 'CLSID\{A3FCE0F5-3493-419F-958A-ABA1250EC20B}';

function ObsVirtualCamInstalled(): Boolean;
begin
  Result := RegKeyExists(HKCR, ObsVirtualCamClsid);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and not ObsVirtualCamInstalled() then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
      'Attenzione: la webcam virtuale di OBS non risulta installata. Installa OBS Studio 30 o ' +
      'successivo da obsproject.com, avvia e ferma una volta la sua videocamera virtuale, poi ' +
      'chiudi OBS. Senza questo passaggio Teams non vede ShinobiCam.';
end;
