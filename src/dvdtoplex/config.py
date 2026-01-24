"""Configuration management for DVD to Plex."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from current directory or parent directories
load_dotenv()

# Default auto-approve threshold for content identification
DEFAULT_AUTO_APPROVE_THRESHOLD = 0.85


@dataclass
class Config:
    """Application configuration."""

    pushover_user_key: str = ""
    pushover_api_token: str = ""
    tmdb_api_token: str = ""
    anthropic_api_key: str = ""
    workspace_dir: Path = field(default_factory=lambda: Path.home() / "DVDWorkspace")
    plex_movies_dir: Path = field(default_factory=lambda: Path("/Volumes/Media8TB/Movies"))
    plex_tv_dir: Path = field(default_factory=lambda: Path("/Volumes/Media8TB/TV Shows"))
    plex_home_movies_dir: Path = field(default_factory=lambda: Path("/Volumes/Media8TB/Home Movies"))
    plex_other_dir: Path = field(default_factory=lambda: Path("/Volumes/Media8TB/Other"))
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    active_mode: bool = False
    drive_poll_interval: float = 15.0
    auto_approve_threshold: float = DEFAULT_AUTO_APPROVE_THRESHOLD
    drive_ids: list[str] = field(default_factory=lambda: ["0", "1"])
    google_sheets_credentials_file: Path | None = None
    google_sheets_spreadsheet_id: str | None = None
    sheets_sync_interval: int = 24  # hours

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.auto_approve_threshold <= 1.0:
            raise ValueError(
                f"auto_approve_threshold must be between 0.0 and 1.0, got {self.auto_approve_threshold}"
            )
        # Convert string paths to Path objects if needed
        if isinstance(self.workspace_dir, str):
            self.workspace_dir = Path(self.workspace_dir)
        if isinstance(self.plex_movies_dir, str):
            self.plex_movies_dir = Path(self.plex_movies_dir)
        if isinstance(self.plex_tv_dir, str):
            self.plex_tv_dir = Path(self.plex_tv_dir)
        if isinstance(self.plex_home_movies_dir, str):
            self.plex_home_movies_dir = Path(self.plex_home_movies_dir)
        if isinstance(self.plex_other_dir, str):
            self.plex_other_dir = Path(self.plex_other_dir)

    @property
    def staging_dir(self) -> Path:
        """Directory for staging ripped files."""
        return self.workspace_dir / "staging"

    @property
    def encoding_dir(self) -> Path:
        """Directory for encoded files."""
        return self.workspace_dir / "encoding"


def load_config() -> Config:
    """Load configuration from environment variables."""
    auto_threshold_str = os.getenv("AUTO_APPROVE_THRESHOLD", str(DEFAULT_AUTO_APPROVE_THRESHOLD))
    try:
        auto_threshold = float(auto_threshold_str)
    except ValueError:
        auto_threshold = DEFAULT_AUTO_APPROVE_THRESHOLD

    # Parse drive_ids from comma-separated string
    drive_ids_str = os.getenv("DRIVE_IDS", "0,1")
    drive_ids = [d.strip() for d in drive_ids_str.split(",") if d.strip()]

    # Google Sheets config
    sheets_creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
    sheets_creds_path = Path(sheets_creds).expanduser() if sheets_creds else None

    return Config(
        pushover_user_key=os.getenv("PUSHOVER_USER_KEY", ""),
        pushover_api_token=os.getenv("PUSHOVER_API_TOKEN", ""),
        tmdb_api_token=os.getenv("TMDB_API_TOKEN", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        workspace_dir=Path(os.getenv("WORKSPACE_DIR", str(Path.home() / "DVDWorkspace"))).expanduser(),
        plex_movies_dir=Path(os.getenv("PLEX_MOVIES_DIR", "/Volumes/Media8TB/Movies")).expanduser(),
        plex_tv_dir=Path(os.getenv("PLEX_TV_DIR", "/Volumes/Media8TB/TV Shows")).expanduser(),
        plex_home_movies_dir=Path(os.getenv("PLEX_HOME_MOVIES_DIR", "/Volumes/Media8TB/Home Movies")).expanduser(),
        plex_other_dir=Path(os.getenv("PLEX_OTHER_DIR", "/Volumes/Media8TB/Other")).expanduser(),
        web_host=os.getenv("WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("WEB_PORT", "8080")),
        active_mode=os.getenv("ACTIVE_MODE", "false").lower() == "true",
        drive_poll_interval=float(os.getenv("DRIVE_POLL_INTERVAL", "15.0")),
        auto_approve_threshold=auto_threshold,
        drive_ids=drive_ids,
        google_sheets_credentials_file=sheets_creds_path,
        google_sheets_spreadsheet_id=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"),
        sheets_sync_interval=int(os.getenv("SHEETS_SYNC_INTERVAL", "24")),
    )
