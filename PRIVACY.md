# Privacy Policy for ReelHaul

**Effective Date:** November 2026

ReelHaul is a free, open-source desktop application designed with user privacy in mind. 

## 1. Data Collection & Telemetry
ReelHaul **does not** collect, store, transmit, or sell any personal data, usage analytics, or telemetry to the developer or any third-party analytics servers.

## 2. Local Data Storage
All application data remains strictly on your local Windows machine:
* **Settings & Logs:** Your preferences (such as save folder and quality toggles) are stored locally in `%APPDATA%\ReelHaul\settings.json`, and diagnostic logs are stored in `%APPDATA%\ReelHaul\reelhaul.log`.
* **Browser Cookies (Optional):** If you enable the browser cookie feature to access age-restricted or members-only videos, ReelHaul reads cookies locally from your selected browser solely to pass them to the `yt-dlp` engine for that specific download session. Cookies are never transmitted anywhere other than the target media host.

## 3. Third-Party Services
When you analyze or download a link, ReelHaul connects directly to the target website (such as YouTube) via `yt-dlp`, as well as optional third-party services like SponsorBlock if enabled. When you use the **Update engine** feature, ReelHaul connects to GitHub/PyPI to download the latest `yt-dlp` release. Your interactions with these external services are governed by their respective privacy policies.

## 4. Contact
If you have questions about this privacy policy or the source code, please open an issue on the [ReelHaul GitHub Repository](https://github.com).
