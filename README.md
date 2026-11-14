# ReelHaul

A free, ad-free desktop downloader for Windows. Paste a YouTube link (or any of
1000+ other sites yt-dlp supports) and grab it in up to **8K**, with playlists,
MP3, subtitles, thumbnails and more. No accounts, no limits, no paywalls.

![ReelHaul](assets/logo.png)

## Quick start

- **Installed with the Setup file?** Just launch **ReelHaul** from your Start
  menu or desktop. Everything (the downloader engine, ffmpeg for 4K merging,
  and a JavaScript runtime so 4K/8K formats appear) is installed with it —
  no Python needed.
- **Running from this folder?** Double-click `ReelHaul.bat`. On a fresh machine,
  run `setup.bat` once — it creates a private Python environment and installs
  everything.
- **Debugging:** `ReelHaul (console).bat` shows errors in a console window.

### How to use

1. Paste one or more links (one per line) into **Links**. `Paste` reads your
   clipboard; pressing **Enter** in a fresh box also works.
2. Optional: press **Analyze** to see the thumbnail, title, channel and which
   resolutions are actually available. The quality list updates to match.
3. Pick a quality, then press **Download** (or `Ctrl+Enter`).
4. Watch the queue. Hover a row and use **✕** to cancel, **Open** to reveal the
   finished file in Explorer, or **Retry** after a failure.

## What you can grab

| Setting | Notes |
| --- | --- |
| Quality | Best available (up to 8K), 4K, 2K, 1080p, 720p, 480p, 360p, or audio only (MP3 320 kbps / M4A). If a height isn't available for that video it falls back to the best one that is. |
| Container | MP4 (recommended) or MKV. |
| Subtitles (EN) | Downloads and embeds English subtitles, including auto-generated ones. |
| Thumbnail | Embeds the cover image into the file. |
| Metadata | Writes title, artist, and chapter info. |
| SponsorBlock | Skips sponsor/self-promo/intro/outro segments while saving. |
| Full playlist | Download every video in a playlist instead of just the one you linked. |
| Cookies | Use your signed-in browser (Firefox, Chrome, Edge, Brave, Opera, Vivaldi) for age-restricted videos, members-only videos, and YouTube's "confirm you're not a bot" checks. **Firefox is the most reliable** — Chrome's cookie encryption is getting stricter on Windows. |

## Good to know about 4K

- YouTube serves 4K/8K as **VP9 or AV1** video, often with Opus audio, merged
  into MP4. VLC, MPV, Chrome, Edge and Windows 11 players handle it fine.
- If a device or player can't play those codecs, tick **H.264 only** — that caps
  YouTube at 1080p because H.264 doesn't exist above that there.
- Some 4K videos are **HDR**; on an SDR monitor they can look washed out in weak
  players. Pick a lower height if that bothers you.
- For YouTube's full format list, ReelHaul uses the official `yt-dlp-ejs`
  challenge solver with whatever JS runtime it finds (Deno, Node, Bun or
  QuickJS). If formats ever look missing, update the engine (see below).

## Keeping it working

YouTube changes things constantly. If downloads start failing:

1. Press **Update engine** (top right). In an installed ReelHaul this runs the
   official engine's self-updater (`yt-dlp --update`) and offers to restart the
   app. When running from source it runs `pip install -U yt-dlp` instead.
2. Still failing? Close and reopen the app; the new engine loads at startup.
3. ffmpeg is required for merging 4K video/audio, MP3 conversion, thumbnails and
   subtitle embedding. The Setup file installs a bundled copy; when running from
   source, ReelHaul finds ffmpeg on PATH automatically.

Settings (save folder, toggles, window position) live in
`%APPDATA%\ReelHaul\settings.json`; logs go to `%APPDATA%\ReelHaul\reelhaul.log`.

## Files

```
ReelHaul/
├─ app.py                      the GUI
├─ engine.py                   yt-dlp subprocess wrapper (queue, progress, cancel)
├─ make_assets.py              regenerates the icon/logo
├─ make_installer_art.py       regenerates the installer wizard art
├─ requirements.txt            dependencies (source builds only)
├─ setup.bat                   one-time install for running from source
├─ ReelHaul.bat                launcher when running from source
├─ ReelHaul (console).bat      launcher with a console for debugging
├─ ReelHaul.spec               PyInstaller spec for the standalone app
├─ installer.iss               Inno Setup script for the dark-branded installer
├─ license.txt                 MIT-style license + fair-use note + credits
├─ build.bat                   one command: exe + installer -> release\
├─ bundled/                    yt-dlp.exe, ffmpeg, deno.exe shipped with Setup
├─ dist/ReelHaul/              packaged app (build output)
└─ release/                    ReelHaul-Setup-*.exe (build output)
```

## Building the installer yourself

1. Install Python 3.10+ and run `setup.bat` once.
2. `winget install -e --id JRSoftware.InnoSetup`
3. Run `build.bat` — it produces `dist\ReelHaul\ReelHaul.exe` (the standalone
   app) and `release\ReelHaul-Setup-<version>.exe` (the installer, with ffmpeg,
   yt-dlp and a JS runtime bundled, so it works on any Windows 10/11 PC).
4. Sanity check a build with `ReelHaul.exe --selftest` (exit code 0 and a JSON
   report in `%APPDATA%\ReelHaul\selftest.json`).

Note: the Setup file is not code-signed, so Windows SmartScreen may ask you to
confirm it on first run ("More info" → "Run anyway"). See *Code signing* below.

## Code signing

Releases are code-signed through the **SignPath Foundation** free code-signing
program for open-source projects — the published policy is in
[CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md). How it works:

1. The GitHub Actions workflow (`.github/workflows/release.yml`) builds the app
   and installer on a clean Windows runner, self-tests it, and submits the
   artifact to SignPath for signing.
2. A project approver approves the signing request in the SignPath web UI,
   and the signed installer is attached to the GitHub release.
3. To enable it, set the repository **variables** `SIGNPATH_ORGANIZATION_ID`
   (+ optional `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG`) and the
   **secret** `SIGNPATH_API_TOKEN`. Without them the workflow still builds and
   publishes, just unsigned.

For local builds you can sign manually instead: put a certificate at
`signing\cert.pfx` and run `setx REELHAUL_CERT_PASSWORD "your password"` before
`build.bat` (`signing\sign.ps1` handles SHA-256 digest + RFC 3161 timestamp and
verifies the result). No certificate? The build simply stays unsigned.

## Fair use

ReelHaul is a front-end for the open-source project
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Download only videos you own or have
permission to save, and respect the terms of service of whatever site you use it
with.
