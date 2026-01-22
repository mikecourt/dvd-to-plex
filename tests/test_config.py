"""Tests for configuration module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dvdtoplex.config import Config, DEFAULT_AUTO_APPROVE_THRESHOLD, load_config


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self) -> None:
        """Config should have sensible defaults."""
        config = Config()
        assert config.pushover_user_key == ""
        assert config.pushover_api_token == ""
        assert config.tmdb_api_token == ""
        assert config.web_host == "127.0.0.1"
        assert config.web_port == 8080
        assert config.drive_poll_interval == 5.0
        assert config.auto_approve_threshold == DEFAULT_AUTO_APPROVE_THRESHOLD

    def test_auto_approve_threshold_default(self) -> None:
        """Default auto-approve threshold should be 0.85."""
        assert DEFAULT_AUTO_APPROVE_THRESHOLD == 0.85
        config = Config()
        assert config.auto_approve_threshold == 0.85

    def test_auto_approve_threshold_custom(self) -> None:
        """Auto-approve threshold should be customizable."""
        config = Config(auto_approve_threshold=0.90)
        assert config.auto_approve_threshold == 0.90

    def test_auto_approve_threshold_minimum(self) -> None:
        """Auto-approve threshold can be set to 0.0."""
        config = Config(auto_approve_threshold=0.0)
        assert config.auto_approve_threshold == 0.0

    def test_auto_approve_threshold_maximum(self) -> None:
        """Auto-approve threshold can be set to 1.0."""
        config = Config(auto_approve_threshold=1.0)
        assert config.auto_approve_threshold == 1.0

    def test_auto_approve_threshold_invalid_high(self) -> None:
        """Auto-approve threshold above 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="auto_approve_threshold must be between"):
            Config(auto_approve_threshold=1.1)

    def test_auto_approve_threshold_invalid_low(self) -> None:
        """Auto-approve threshold below 0.0 should raise ValueError."""
        with pytest.raises(ValueError, match="auto_approve_threshold must be between"):
            Config(auto_approve_threshold=-0.1)

    def test_staging_dir_property(self) -> None:
        """staging_dir should be workspace_dir / staging."""
        config = Config(workspace_dir=Path("/test/workspace"))
        assert config.staging_dir == Path("/test/workspace/staging")

    def test_encoding_dir_property(self) -> None:
        """encoding_dir should be workspace_dir / encoding."""
        config = Config(workspace_dir=Path("/test/workspace"))
        assert config.encoding_dir == Path("/test/workspace/encoding")

    def test_config_has_home_movies_dir(self) -> None:
        """Test config has plex_home_movies_dir."""
        config = Config()
        assert hasattr(config, "plex_home_movies_dir")
        assert isinstance(config.plex_home_movies_dir, Path)

    def test_config_has_other_dir(self) -> None:
        """Test config has plex_other_dir."""
        config = Config()
        assert hasattr(config, "plex_other_dir")
        assert isinstance(config.plex_other_dir, Path)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_config should use defaults when env vars not set."""
        # Clear relevant env vars
        for key in [
            "PUSHOVER_USER_KEY",
            "PUSHOVER_API_TOKEN",
            "TMDB_API_TOKEN",
            "WORKSPACE_DIR",
            "PLEX_MOVIES_DIR",
            "PLEX_TV_DIR",
            "WEB_HOST",
            "WEB_PORT",
            "DRIVE_POLL_INTERVAL",
            "AUTO_APPROVE_THRESHOLD",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = load_config()

        assert config.auto_approve_threshold == DEFAULT_AUTO_APPROVE_THRESHOLD

    def test_load_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_config should read AUTO_APPROVE_THRESHOLD from environment."""
        monkeypatch.setenv("AUTO_APPROVE_THRESHOLD", "0.90")
        monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
        monkeypatch.delenv("PUSHOVER_API_TOKEN", raising=False)
        monkeypatch.delenv("TMDB_API_TOKEN", raising=False)

        config = load_config()

        assert config.auto_approve_threshold == 0.90

    def test_load_config_threshold_boundary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_config should handle boundary values for threshold."""
        # Test 0.0
        monkeypatch.setenv("AUTO_APPROVE_THRESHOLD", "0.0")
        config = load_config()
        assert config.auto_approve_threshold == 0.0

        # Test 1.0
        monkeypatch.setenv("AUTO_APPROVE_THRESHOLD", "1.0")
        config = load_config()
        assert config.auto_approve_threshold == 1.0

    def test_load_config_home_movies_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test load_config loads plex_home_movies_dir from env."""
        monkeypatch.setenv("PLEX_HOME_MOVIES_DIR", "/test/home/movies")
        config = load_config()
        assert config.plex_home_movies_dir == Path("/test/home/movies")

    def test_load_config_other_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test load_config loads plex_other_dir from env."""
        monkeypatch.setenv("PLEX_OTHER_DIR", "/test/other")
        config = load_config()
        assert config.plex_other_dir == Path("/test/other")
