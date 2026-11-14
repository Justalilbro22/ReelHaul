# SignPath Foundation application draft
# Apply at: https://signpath.org/  →  "Apply for open source code signing"
# Only YOUR personal name/email goes in; everything else is below.
# (Not committed to the repo - local reference only.)

Project name:            TubeGrab
Public source repository: https://github.com/Justalilbro22/TubeGrab
Latest release:          https://github.com/Justalilbro22/TubeGrab/releases (v1.0.0)
License:                 MIT (OSI-approved, no dual licensing, no proprietary code)
Homepage / policy page:  https://github.com/Justalilbro22/TubeGrab
                         (code signing policy: CODE_SIGNING_POLICY.md in the repo root)

PROJECT DESCRIPTION
-------------------
TubeGrab is a free, open-source desktop application for Windows that downloads
videos and audio from YouTube and 1000+ other supported sites. It offers every
quality up to 8K/4K, MP3/M4A audio extraction, playlist downloads, subtitle and
thumbnail embedding, and built-in SponsorBlock support, behind a clean
dark-themed GUI. It is a friendly front-end for the yt-dlp project, bundled
with ffmpeg and a JavaScript runtime so that non-technical users get the full
quality range working out of the box.

WHAT THE PROJECT SIGNS
----------------------
Only first-party binaries produced by the project's GitHub Actions workflow:
the application executable (TubeGrab.exe) and its installer
(TubeGrab-Setup-<version>.exe). Upstream third-party binaries (yt-dlp, ffmpeg,
deno) are downloaded at build time from their official release pages and are
shipped unmodified inside the installer without being signed by this
certificate.

TEAM
----
One maintainer (me), acting as author, reviewer and approver:
- Commits to the repository (I am the only committer; no other authors)
- Pull requests from others are reviewed before merging
- Every signing request is manually approved in the SignPath web UI before release
- My GitHub account has two-factor authentication enabled

BUILD & INTEGRITY
-----------------
Releases are built exclusively by the GitHub Actions workflow in the public
repository (windows-latest runner). The workflow:
1. checks out the exact git tag being released,
2. fetches third-party tools from official upstream URLs,
3. runs a functional self-test of the built application,
4. submits the artifact to SignPath via the official
   signpath/github-action-submit-signing-request integration,
5. attaches the signed installer to the GitHub release.
The published signing policy (CODE_SIGNING_POLICY.md) documents all of this.
