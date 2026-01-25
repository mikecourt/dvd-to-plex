# Google Sheets Sync Design

## Overview

Sync owned movies and wishlist to a Google Sheet with two tables for tracking and searching the collection.

## Requirements

- Two-sheet Google Sheet:
  - **Owned**: Movies from Plex directory (title, year)
  - **Wishlist**: Wanted items from database (title, year, poster URL, embedded poster image)
- Daily automatic sync
- Use Google Sheets Tables feature for sorting/filtering
- Service account authentication

## Architecture

### New Files

1. **`src/dvdtoplex/google_sheets.py`** - Google Sheets API client
   - Service account authentication
   - Table creation and updates
   - IMAGE() formula generation for posters

2. **`src/dvdtoplex/services/sheets_sync.py`** - Background sync service
   - Inherits from `BaseService`
   - Daily sync interval (configurable)
   - Scans Plex directories, reads wanted table, pushes to Sheets

### Configuration

New environment variables in `.env`:

```
GOOGLE_SHEETS_CREDENTIALS_FILE=/path/to/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=abc123xyz
SHEETS_SYNC_INTERVAL=24  # hours, default 24
```

### Dependencies

Add to `pyproject.toml`:
- `gspread` - Google Sheets API wrapper

## Sheet Structure

### Sheet 1: "Owned"

Table name: `OwnedMovies`

| Title | Year |
|-------|------|
| The Matrix | 1999 |
| Inception | 2010 |

- Column types: Text, Number
- Populated by scanning `plex_movies_dir`

### Sheet 2: "Wishlist"

Table name: `Wishlist`

| Title | Year | Poster URL | Poster |
|-------|------|------------|--------|
| Dune | 2021 | https://image.tmdb.org/... | =IMAGE(...) |

- Column types: Text, Number, URL, Image formula
- Populated from SQLite `wanted` table

## Plex Directory Scanning

Scans `plex_movies_dir` (default `/Volumes/Media8TB/Movies`).

**Naming convention:** `Movie Title (Year)/Movie Title (Year).ext`

**Parser logic:**
1. List immediate subdirectories
2. Extract title/year via regex: `^(.+?)\s*\((\d{4})\)$`
3. Skip hidden folders (starting with `.`)
4. Movies without year in folder name included with blank year

## Sync Process

**Strategy:** Full replace on each sync

**Flow:**
1. Timer fires (every 24 hours)
2. Scan Plex movies directory → list of (title, year)
3. Query SQLite `wanted` table → list of WantedItems
4. Clear "Owned" table data (preserve headers)
5. Write all owned movies
6. Clear "Wishlist" table data (preserve headers)
7. Write all wanted items with `=IMAGE()` formulas for posters
8. Log sync completion

**First sync:** Runs immediately on startup if configured, then switches to daily schedule.

## Google Sheets Tables

Uses the [Google Sheets Tables API](https://developers.google.com/workspace/sheets/api/guides/tables) (added May 2024).

Tables provide:
- Built-in sorting and filtering
- Column type enforcement
- Auto-expanding ranges
- Alternating row colors
- Named table references

Created via `batchUpdate` with `addTable` request since gspread lacks native wrapper.

## Error Handling

- **Missing credentials:** Log warning, skip sync service (don't crash app)
- **Invalid credentials:** Fail fast on startup with clear error
- **Network failure:** Log error, retry on next cycle
- **Missing Plex directory:** Log warning, write empty table
- **API rate limits:** Exponential backoff retry

## Setup Instructions

1. Create Google Cloud project, enable Sheets API
2. Create service account, download JSON key
3. Create Google Sheet with two tabs: "Owned" and "Wishlist"
4. Share sheet with service account email (Editor access)
5. Add credentials path and spreadsheet ID to `.env`
6. Restart application

## Integration

- `SheetsSyncService` follows existing service pattern
- Started in `main.py` alongside other services
- Gracefully disabled if not configured
