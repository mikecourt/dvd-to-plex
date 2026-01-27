#!/usr/bin/env python3
"""Enrich wishlist items with year and poster data from TMDb.

Supports both one-time and continuous (periodic) operation modes.
Only processes items missing year or poster data.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from dvdtoplex.google_sheets import GoogleSheetsClient, format_poster_url, format_image_formula
from dvdtoplex.tmdb import TMDbClient

load_dotenv()


def needs_enrichment(row: list) -> bool:
    """Check if a row needs enrichment (missing year).

    Args:
        row: Sheet row with [Poster, Title, Year] columns.
             Values may be strings or integers depending on content.

    Returns:
        True if the row is missing year data.
        Note: We only check for year since some movies may not have posters
        in TMDb, and we don't want to re-process them endlessly.
    """
    if len(row) < 2:
        return False  # No title, skip

    # Convert all values to strings for consistent handling
    title = str(row[1]).strip() if len(row) > 1 and row[1] else ""
    year = str(row[2]).strip() if len(row) > 2 and row[2] else ""

    # Skip if no title
    if not title:
        return False

    # Needs enrichment if missing year (poster may be unavailable for some movies)
    return not year


async def enrich_missing_items(sheets_client: GoogleSheetsClient, tmdb_token: str) -> int:
    """Find and enrich items missing year or poster data.

    Args:
        sheets_client: Connected Google Sheets client.
        tmdb_token: TMDb API token.

    Returns:
        Number of items enriched.
    """
    spreadsheet = sheets_client._get_spreadsheet()
    worksheet = spreadsheet.worksheet("Wishlist")
    # Use FORMULA render option to get actual formulas (like =IMAGE(...)) instead of displayed values
    all_values = worksheet.get_all_values(value_render_option="FORMULA")

    if len(all_values) <= 1:
        print("No items in wishlist (only header)")
        return 0

    # Find rows needing enrichment (skip header at index 0)
    rows_to_enrich = []
    for row_idx, row in enumerate(all_values[1:], start=2):  # Sheet rows are 1-indexed, +1 for header
        if needs_enrichment(row):
            title = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            existing_year = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            rows_to_enrich.append({
                "row_num": row_idx,
                "title": title,
                "existing_year": existing_year,
            })

    if not rows_to_enrich:
        print("All items already have poster and year data")
        return 0

    print(f"Found {len(rows_to_enrich)} items needing enrichment")

    # Enrich with TMDb data
    updates = []
    async with TMDbClient(tmdb_token) as tmdb:
        for i, item in enumerate(rows_to_enrich):
            title = item["title"]
            print(f"[{i+1}/{len(rows_to_enrich)}] Searching TMDb for: {title}")

            # Try to parse year from existing data
            year_hint = None
            if item["existing_year"]:
                try:
                    year_hint = int(item["existing_year"])
                except ValueError:
                    pass

            # Search TMDb
            results = await tmdb.search_movie(title, year=year_hint)

            if results:
                match = results[0]
                poster_url = format_poster_url(match.poster_path)
                image_formula = format_image_formula(poster_url)

                updates.append({
                    "row_num": item["row_num"],
                    "poster": image_formula,
                    "title": match.title,
                    "year": match.year or "",
                })
                print(f"  -> Found: {match.title} ({match.year})")
            else:
                print(f"  -> No results found, skipping")

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.25)

    # Apply updates to specific cells
    if updates:
        print(f"\nUpdating {len(updates)} rows in Google Sheets...")
        for update in updates:
            row_num = update["row_num"]
            # Update cells A, B, C for this row
            worksheet.update(
                values=[[update["poster"], update["title"], update["year"]]],
                range_name=f"A{row_num}:C{row_num}",
                value_input_option="USER_ENTERED",
            )
        print("Updates complete!")

    return len(updates)


async def run_once(sheets_client: GoogleSheetsClient, tmdb_token: str) -> None:
    """Run enrichment once."""
    enriched = await enrich_missing_items(sheets_client, tmdb_token)
    print(f"\nEnriched {enriched} items")


async def run_continuous(sheets_client: GoogleSheetsClient, tmdb_token: str, interval: int) -> None:
    """Run enrichment continuously at specified interval.

    Args:
        sheets_client: Connected Google Sheets client.
        tmdb_token: TMDb API token.
        interval: Seconds between checks.
    """
    print(f"Running in continuous mode, checking every {interval} seconds")
    print("Press Ctrl+C to stop\n")

    while True:
        try:
            enriched = await enrich_missing_items(sheets_client, tmdb_token)
            if enriched > 0:
                print(f"Enriched {enriched} items")
            else:
                print("No new items to enrich")

            print(f"\nWaiting {interval} seconds until next check...")
            await asyncio.sleep(interval)
            print("\n" + "="*50 + "\n")
        except KeyboardInterrupt:
            print("\nStopping continuous mode")
            break


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich wishlist items with year and poster data from TMDb"
    )
    parser.add_argument(
        "--continuous", "-c",
        action="store_true",
        help="Run continuously, checking for new items periodically"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=300,
        help="Seconds between checks in continuous mode (default: 300)"
    )
    args = parser.parse_args()

    # Get config from environment
    credentials_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    tmdb_token = os.getenv("TMDB_API_TOKEN")

    if not credentials_file or not spreadsheet_id:
        print("Error: Google Sheets config not set in .env")
        print("  Required: GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEETS_SPREADSHEET_ID")
        sys.exit(1)

    if not tmdb_token:
        print("Error: TMDB_API_TOKEN not set in .env")
        sys.exit(1)

    # Connect to Google Sheets
    sheets_client = GoogleSheetsClient(
        credentials_file=Path(credentials_file),
        spreadsheet_id=spreadsheet_id,
    )
    sheets_client.connect()

    if args.continuous:
        await run_continuous(sheets_client, tmdb_token, args.interval)
    else:
        await run_once(sheets_client, tmdb_token)


if __name__ == "__main__":
    asyncio.run(main())
