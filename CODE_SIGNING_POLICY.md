# ReelHaul code signing policy

Every official binary release of ReelHaul is code-signed through the
[SignPath Foundation](https://signpath.org) free code-signing program for
open-source projects. This page is the project's published signing policy, as
required by the Foundation.

## What is signed

| File | What it is |
| --- | --- |
| `ReelHaul-Setup-&lt;version&gt;.exe` | The installer (Inno Setup), signed |
| `ReelHaul.exe` | The application executable, signed (also inside the installer) |

Upstream third-party binaries (yt-dlp.exe, ffmpeg.exe, ffprobe.exe, deno.exe)
are **not** signed with the project certificate. They are downloaded at build
time from the official upstream release URLs listed below and are shipped
unmodified inside the installer.

## How a release gets signed

1. A release is built **only** by the GitHub Actions workflow
   (`.github/workflows/release.yml`) on `windows-latest`, from the git tag that
   matches the release (e.g. `v1.0.0`).
2. The workflow fetches the bundled third-party tools directly from their
   official upstream release pages:
   - `yt-dlp.exe` — https://github.com/yt-dlp/yt-dlp/releases
   - `deno.exe` — https://github.com/denoland/deno/releases
   - `ffmpeg.exe` / `ffprobe.exe` — https://github.com/BtbN/FFmpeg-Builds/releases
3. The build runs a self-test (`ReelHaul.exe --selftest`) which must pass
   before any artifact is submitted for signing.
4. A signing request is submitted to SignPath.io from the same workflow run
   using the official GitHub Actions integration; SignPath verifies that the
   artifact originates from this repository's CI before it can be signed.
5. The signing request must be **manually approved** by a project approver in
   the SignPath web UI before the certificate is applied.
6. The signed installer is attached to the corresponding GitHub release.

## Provenance and integrity

- Signing requests come from `refs/tags/v*` workflow runs of this repository
  ( enforced by SignPath's pipeline integrity verification and the policy
  conditions in the SignPath project configuration).
- All project files are under an OSI-approved MIT license (see `LICENSE`);
  the project contains no proprietary code and is not dual-licensed.
- Every release on GitHub states whether it is signed. Until the SignPath
  Foundation project is approved, releases carry the unsigned build produced by
  this same workflow; once approved, **only** signed installers are published
  as releases.

## Verifying a download

After installing, right-click `ReelHaul.exe` → *Properties* → *Digital
Signatures* and confirm the signer is the **SignPath Foundation: ReelHaul**
certificate.
