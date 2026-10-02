#define AppVersion "0.2.2"
[Setup]
AppId={{CDB95992-B140-4B7F-9D20-8ACB5151153D}
AppName=OpenStack VDI
AppVersion={#AppVersion}
AppPublisher=OpenStack VDI contributors
AppPublisherURL=https://github.com/popododo0720/openstack-vdi
DefaultDirName={autopf}\OpenStackVDI
DefaultGroupName=OpenStack VDI
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\dist\installer
OutputBaseFilename=OpenStackVDI-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\OpenStackVDI.exe
LicenseFile=..\LICENSE

[Files]
Source: "..\dist\OpenStackVDI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\initialize-windows-endpoint.ps1"; DestDir: "{app}\setup"; Flags: ignoreversion
Source: "..\scripts\setup-windows-rustdesk.ps1"; DestDir: "{app}\setup"; Flags: ignoreversion

[Icons]
Name: "{commondesktop}\OpenStack VDI"; Filename: "{app}\OpenStackVDI.exe"; WorkingDir: "{app}"
Name: "{group}\OpenStack VDI"; Filename: "{app}\OpenStackVDI.exe"; WorkingDir: "{app}"

[Code]
var
  EnrollmentPage: TInputFileWizardPage;

procedure InitializeWizard;
begin
  EnrollmentPage := CreateInputFilePage(wpSelectDir, 'Company connection settings',
    'Choose the enrollment JSON provided by your administrator.',
    'Passwords are not included in this file. Existing settings are preserved during upgrades.');
  EnrollmentPage.Add('Enrollment JSON:', 'JSON files|*.json', '.json');
  EnrollmentPage.Values[0] := ExpandConstant('{param:ENROLLMENT|}');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = EnrollmentPage.ID) and FileExists(ExpandConstant('{app}\deployment.json'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not FileExists(ExpandConstant('{app}\deployment.json')) and not FileExists(EnrollmentPage.Values[0]) then
    Result := 'Choose an administrator-provided enrollment JSON before installing.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Params: String;
  Code: Integer;
begin
  if CurStep = ssPostInstall then begin
    Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\setup\initialize-windows-endpoint.ps1') + '" -InstallDirectory "' + ExpandConstant('{app}') + '"';
    if EnrollmentPage.Values[0] <> '' then Params := Params + ' -EnrollmentPath "' + EnrollmentPage.Values[0] + '"';
    if ExpandConstant('{param:RUSTDESKINSTALLER|}') <> '' then Params := Params + ' -RustDeskInstaller "' + ExpandConstant('{param:RUSTDESKINSTALLER|}') + '"';
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      RaiseException('Endpoint configuration failed. Check the enrollment file and RustDesk installation, then run Setup again.');
  end;
end;
