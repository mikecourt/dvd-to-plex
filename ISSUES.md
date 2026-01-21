# DVD-to-Plex Issues & Future Work

## Self-Healing Features (From Design Doc)

These features were designed but not implemented:

### High Priority

- [ ] **Active Mode Monitoring** - Alert when drive is idle >5 min with no disc
- [ ] **Periodic Health Check** - Run `drutil status` every 60s, attempt auto-mount if disc present but not mounted
- [ ] **Duplicate Detection** - Check Collection DB before encoding to avoid re-ripping owned content

### Medium Priority

- [ ] **Disc Read Error Recovery** - Retry MakeMKV with different settings (slower read speed, skip bad sectors)
- [ ] **Partial Rip Handling** - If >90% complete, proceed with warning
- [ ] **Encoding Failure Recovery** - Restart failed HandBrake jobs, try fallback settings on repeated failures
- [ ] **Drive Disconnect Handling** - Pause job on disconnect, resume when reconnected

### Lower Priority

- [ ] **Multi-Disc Set Handling** - Detect disc mismatch, hold in staging, prompt for correct disc
- [ ] **Season Abandonment** - After 7 days idle on incomplete season, prompt user via Pushover
- [ ] **Smart Escalation Messages** - Include what happened, what was tried, what's needed from user

## Other Missing Features

- [ ] **Tesseract OCR** - Extract text from subtitles for identification hints
- [ ] **Full TV Season Support** - Currently stubbed, only movies fully work
- [ ] **launchd Installation** - Scripts exist but not auto-installed

## Current Bugs

- [ ] **HandBrake --optimize flag** - Can hang on large files (removed from code, needs app restart)
- [ ] **Identify endpoint 404** - Was using in-memory state, fixed to use database (needs restart)
- [ ] **Skip button "job not found"** - Review page shows jobs but skip returns 404. Debug logging added to show requested job ID vs actual REVIEW job IDs. Needs investigation after restart.

## Recently Fixed

- [x] FileMover not integrated into main.py
- [x] Screenshot extraction not implemented
- [x] Claude AI identification not implemented
- [x] Disc label cleanup missing patterns (US_DES, 16X9, PS)
- [x] Review page not reading from database
- [x] TMDb API key not loading from .env
