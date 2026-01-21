# DVD-to-Plex Issues & Future Work

## Self-Healing Features (From Design Doc)

These features were designed but not implemented:

### High Priority

- [ ] **Active Mode Monitoring** - Alert when drive is idle >5 min with no disc
- [ ] **Periodic Health Check** - Run `drutil status` every 60s, attempt auto-mount if disc present but not mounted
- [ ] **Duplicate Detection** - Check Collection DB before encoding to avoid re-ripping owned content
- [ ] **State Consistency Check** - AI should catch impossible states like multiple ENCODING jobs (only 1 allowed), multiple RIPPING on same drive, jobs stuck in transient states too long (RIPPING/ENCODING >24h = likely crashed)

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
- [ ] **TV show identification test failing** - Test expects disc labels with "S1" to prioritize TV results over movie results, but currently returns movie match. Separate from pre-identify issue.

## Recently Fixed

- [x] FileMover not integrated into main.py
- [x] Screenshot extraction not implemented
- [x] Claude AI identification not implemented
- [x] Disc label cleanup missing patterns (US_DES, 16X9, PS)
- [x] Review page not reading from database
- [x] TMDb API key not loading from .env
- [x] **Multiple jobs stuck in ENCODING** - Added startup recovery to reset stuck encoding jobs, and proper CancelledError handling to revert to RIPPED on shutdown
- [x] **Pre-identified jobs still go to review** - Changed identifier to skip auto-ID if job has any identified_title (not just confidence==1.0), preventing race conditions
