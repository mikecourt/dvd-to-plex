# Blu-ray Support Design

## Overview

Add Blu-ray disc support for the bottom drive. The bottom drive already has Blu-ray hardware capability; this adds software support.

## Design Decisions

- **Same workflow as DVD**: Rip → Encode → Identify → Move to Plex
- **Same encoding settings**: Use existing HandBrake preset for both DVD and Blu-ray
- **No disc type tracking**: Jobs don't distinguish between DVD and Blu-ray sources
- **Unified detection**: Use MakeMKV for disc detection on all drives (replaces drutil)
- **Slower polling**: 15-second interval (up from 5) to accommodate MakeMKV startup time

## Changes Required

### config.py

Update `DRIVE_POLL_INTERVAL` default from 5 to 15 seconds.

### drives.py

Replace `drutil`-based detection with MakeMKV-based detection.

**New detection flow:**
1. Call `makemkvcon info disc:X` for each configured drive
2. Parse output to determine if a disc is present
3. Extract disc label from MakeMKV output

**Function changes:**
- `check_disc_present(drive_id)` → Use MakeMKV instead of drutil
- `get_disc_label(drive_id)` → Get label from same MakeMKV call
- Remove `parse_drutil_output()` and related drutil functions
- Keep `eject_disc()` using drutil (works fine for both DVD and Blu-ray)

### makemkv.py

Add or modify function for disc presence detection. May be able to reuse existing `get_disc_info()` or add a lightweight check.

### drive_watcher.py

Minimal changes to use new detection functions from `drives.py`.

## No Changes Required

| Component | Reason |
|-----------|--------|
| `rip_queue.py` | MakeMKV already handles Blu-ray |
| `encode_queue.py` | HandBrake preset works for any input |
| `handbrake.py` | No source-specific logic |
| `identifier.py` | Works on encoded file, not source |
| `file_mover.py` | Works on encoded file, not source |
| Database schema | No new fields needed |
| Web UI | No changes needed |

## Practical Considerations

- **Disk space**: Blu-ray rips are ~20-40GB raw (vs ~4-8GB for DVD). Ensure staging directory has sufficient space.
- **Encode time**: Blu-ray encodes take longer (~2-4 hours vs ~30-60 min for DVD) due to 1080p source resolution.
- **Output size**: Encoded Blu-ray files will be larger than DVD due to higher resolution.

## Testing

- Unit tests for new MakeMKV detection parsing
- Manual test with actual Blu-ray disc in bottom drive
