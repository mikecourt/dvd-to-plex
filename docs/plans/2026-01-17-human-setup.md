# DVD-to-Plex Human Setup Checklist

> **Purpose:** Complete these manual setup steps before Claude begins implementation.

**Estimated Time:** 30-60 minutes

---

## 1. Install MakeMKV

- [ ] Download MakeMKV from https://www.makemkv.com/download/
- [ ] Install the application
- [ ] Purchase license key from https://www.makemkv.com/buy/ (or use beta key during beta period)
- [ ] Launch MakeMKV, enter license key via Help → Register
- [ ] Verify CLI is available:
  ```bash
  /Applications/MakeMKV.app/Contents/MacOS/makemkvcon info
  ```
  Should output MakeMKV version info (error about no disc is expected)

## 2. Install Tesseract (for subtitle OCR)

- [ ] Install via Homebrew:
  ```bash
  brew install tesseract
  ```
- [ ] Verify installation:
  ```bash
  tesseract --version
  ```

## 3. Verify ffmpeg (should already be installed)

- [ ] Check ffmpeg is available:
  ```bash
  ffmpeg -version
  ```
- [ ] If not installed:
  ```bash
  brew install ffmpeg
  ```

## 4. Verify HandBrakeCLI (should already be installed)

- [ ] Check HandBrakeCLI is available:
  ```bash
  HandBrakeCLI --version
  ```
- [ ] If not installed:
  ```bash
  brew install --cask handbrake
  ```
  Or download CLI from https://handbrake.fr/downloads2.php

## 5. Set Up Pushover Account

- [ ] Create account at https://pushover.net/
- [ ] Note your **User Key** (shown on dashboard after login)
- [ ] Create an application at https://pushover.net/apps/build
  - Name: `DVD-to-Plex`
  - Type: `Script`
  - Description: `Automated DVD ripping notifications`
- [ ] Note your **API Token/Key** (shown after creating app)
- [ ] Install Pushover app on your phone
- [ ] Test notification works (Pushover has a test button in web UI)

**Save these for later:**
```
PUSHOVER_USER_KEY=<your-user-key>
PUSHOVER_API_TOKEN=<your-api-token>
```

## 6. Connect USB DVD Drives

- [ ] Connect both external USB DVD drives
- [ ] Verify they appear in Disk Utility
- [ ] Note their device identifiers (usually `/dev/disk2`, `/dev/disk3` or similar)
- [ ] Test each drive can mount a disc:
  ```bash
  drutil status
  ```
- [ ] Insert a test DVD in each drive and verify it mounts

## 7. Verify 8TB Media Drive

- [ ] Confirm drive is mounted at `/Volumes/Media8TB/`
- [ ] Verify Plex directories exist:
  ```bash
  ls -la "/Volumes/Media8TB/Movies/"
  ls -la "/Volumes/Media8TB/TV Shows/"
  ```
- [ ] If directories don't exist, create them:
  ```bash
  mkdir -p "/Volumes/Media8TB/Movies/"
  mkdir -p "/Volumes/Media8TB/TV Shows/"
  ```

## 8. Create Local Workspace Directories

- [ ] Create the workspace structure:
  ```bash
  mkdir -p ~/DVDWorkspace/{ripping,encoding,staging,logs,data}
  ```
- [ ] Verify:
  ```bash
  ls -la ~/DVDWorkspace/
  ```

## 9. Verify Python Environment

- [ ] Check Python version (needs 3.11+):
  ```bash
  python3 --version
  ```
- [ ] If needed, install via Homebrew:
  ```bash
  brew install python@3.11
  ```

## 10. Get TMDb API Key (for content identification)

- [ ] Create account at https://www.themoviedb.org/signup
- [ ] Go to Settings → API → Create → Developer
- [ ] Note your **API Read Access Token** (v4 auth)

**Save for later:**
```
TMDB_API_TOKEN=<your-read-access-token>
```

---

## Summary of Credentials Needed

After completing setup, you should have:

| Credential | Source |
|------------|--------|
| `PUSHOVER_USER_KEY` | Pushover dashboard |
| `PUSHOVER_API_TOKEN` | Pushover app creation |
| `TMDB_API_TOKEN` | TMDb API settings |

Claude will prompt you for these during implementation.

---

## Verification Checklist

Run this to verify all tools are ready:

```bash
echo "=== Tool Verification ==="
echo ""
echo "MakeMKV:"
/Applications/MakeMKV.app/Contents/MacOS/makemkvcon info 2>&1 | head -3
echo ""
echo "Tesseract:"
tesseract --version 2>&1 | head -1
echo ""
echo "ffmpeg:"
ffmpeg -version 2>&1 | head -1
echo ""
echo "HandBrakeCLI:"
HandBrakeCLI --version 2>&1 | head -1
echo ""
echo "Python:"
python3 --version
echo ""
echo "Workspace:"
ls ~/DVDWorkspace/
echo ""
echo "Media Drive:"
ls "/Volumes/Media8TB/" 2>&1 | head -5
echo ""
echo "DVD Drives:"
drutil status
```

Once all checks pass, notify Claude to begin implementation.
