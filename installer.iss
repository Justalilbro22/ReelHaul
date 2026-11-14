; ReelHaul installer — dark branded, per-user, self-contained
; Build: ISCC.exe installer.iss

#define ReelHaulName "ReelHaul"
#define ReelHaulVersion "1.1.0"
#define ReelHaulPublisher "ReelHaul"

[Setup]
AppId={{8F2C0E44-9D3B-4A61-8C57-1E5B9A7D2C36}}
AppName={#ReelHaulName}
AppVersion={#ReelHaulVersion}
AppVerName={#ReelHaulName} {#ReelHaulVersion}
AppPublisher={#ReelHaulPublisher}
DefaultDirName={localappdata}\Programs\{#ReelHaulName}
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=ReelHaul-Setup-{#ReelHaulVersion}
SetupIconFile=assets\icon.ico
WizardStyle=modern
WizardImageFile=assets\installer_side.png
WizardSmallImageFile=assets\installer_small.png
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=65536
ArchitecturesAllowed=x64compatible
LicenseFile=license.txt
UninstallDisplayName={#ReelHaulName}
UninstallDisplayIcon={app}\ReelHaul.exe
VersionInfoVersion={#ReelHaulVersion}
VersionInfoDescription={#ReelHaulName} installer
VersionInfoCopyright=Free & open source
VersionInfoProductName={#ReelHaulName}
VersionInfoProductVersion={#ReelHaulVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\ReelHaul\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "bundled\ytdlp\yt-dlp.exe"; DestDir: "{app}\ytdlp"; Flags: ignoreversion
Source: "bundled\ffmpeg\bin\ffmpeg.exe"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion
Source: "bundled\ffmpeg\bin\ffprobe.exe"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion
Source: "bundled\runtime\deno.exe"; DestDir: "{app}\runtime"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "license.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#ReelHaulName}"; Filename: "{app}\ReelHaul.exe"; \
    Comment: "Free 4K video & audio downloader"
Name: "{autodesktop}\{#ReelHaulName}"; Filename: "{app}\ReelHaul.exe"; \
    Tasks: desktopicon; Comment: "Free 4K video & audio downloader"

[Run]
Filename: "{app}\ReelHaul.exe"; Description: "{cm:LaunchProgram,{#ReelHaulName}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
const
  ClBg    = $110C0A;   // #0A0C11
  ClCard  = $1D1511;   // #11151D
  ClText  = $F9F2EE;   // #EEF2F9
  ClMuted = $A6938A;   // #8A93A6

procedure RecolorControls(Parent: TWinControl);
var
  I: Integer;
  C: TControl;
begin
  for I := 0 to Parent.ControlCount - 1 do
  begin
    C := Parent.Controls[I];
    if C is TNewStaticText then
      TNewStaticText(C).Font.Color := ClText
    else if C is TLabel then
      TLabel(C).Font.Color := ClText
    else if C is TNewCheckBox then
      TNewCheckBox(C).Font.Color := ClText
    else if C is TNewCheckListBox then
      TNewCheckListBox(C).Font.Color := ClText
    else if C is TPanel then
      TPanel(C).Color := ClBg
    else if C is TEdit then
    begin
      TEdit(C).Color := ClCard;
      TEdit(C).Font.Color := ClText;
    end
    else if C is TRichEditViewer then
    begin
      TRichEditViewer(C).Color := ClCard;
      TRichEditViewer(C).Font.Color := ClText;
    end;

    if C is TWinControl then
      RecolorControls(TWinControl(C));
  end;
end;

procedure InitializeWizard();
begin
  WizardForm.Color := ClBg;
  WizardForm.MainPanel.Color := ClBg;
  WizardForm.InnerPage.Color := ClBg;
  WizardForm.PageNameLabel.Font.Color := ClText;
  WizardForm.PageDescriptionLabel.Font.Color := ClMuted;
  WizardForm.DirEdit.Color := ClCard;
  WizardForm.DirEdit.Font.Color := ClText;
  WizardForm.LicenseMemo.Color := ClCard;
  WizardForm.LicenseMemo.Font.Color := ClText;
  RecolorControls(WizardForm);
end;
