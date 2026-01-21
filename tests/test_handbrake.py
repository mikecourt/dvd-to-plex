"""Tests for HandBrake wrapper error handling."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from dvdtoplex.handbrake import (
    EncodeError,
    EncodeProgress,
    HandBrakeNotFoundError,
    InputFileError,
    OutputFileError,
    _extract_error_details,
    build_encode_command,
    encode_file,
    parse_progress_line,
)


class TestExtractErrorDetails:
    """Tests for _extract_error_details function."""

    def test_extracts_error_lines(self) -> None:
        """Test extraction of error-related lines."""
        stderr = [
            "Loading file...",
            "Processing...",
            "ERROR: Invalid input file",
            "Failed to read stream",
            "Cleaning up...",
        ]
        result = _extract_error_details(stderr)
        assert "ERROR: Invalid input file" in result
        assert "Failed to read stream" in result
        assert "Loading file" not in result

    def test_limits_output_lines(self) -> None:
        """Test that output is limited to max_lines."""
        stderr = [f"error line {i}" for i in range(20)]
        result = _extract_error_details(stderr, max_lines=5)
        lines = result.split("\n")
        assert len(lines) == 5

    def test_fallback_to_last_lines(self) -> None:
        """Test fallback to last N lines when no error keywords found."""
        stderr = [
            "Line 1",
            "Line 2",
            "Line 3",
            "Line 4",
            "Line 5",
        ]
        result = _extract_error_details(stderr, max_lines=3)
        assert "Line 3" in result
        assert "Line 4" in result
        assert "Line 5" in result
        assert "Line 1" not in result

    def test_empty_stderr(self) -> None:
        """Test handling of empty stderr."""
        result = _extract_error_details([])
        assert result == "No error details available"


class TestBuildEncodeCommand:
    """Tests for build_encode_command function."""

    def test_basic_command(self) -> None:
        """Test building basic encode command."""
        cmd = build_encode_command(
            Path("/input.mkv"),
            Path("/output.mkv"),
        )
        assert "HandBrakeCLI" in cmd
        assert "--input" in cmd
        assert "/input.mkv" in cmd
        assert "--output" in cmd
        assert "/output.mkv" in cmd

    def test_custom_handbrake_path(self) -> None:
        """Test building command with custom HandBrakeCLI path."""
        cmd = build_encode_command(
            Path("/input.mkv"),
            Path("/output.mkv"),
            handbrake_cli="/usr/local/bin/HandBrakeCLI",
        )
        assert cmd[0] == "/usr/local/bin/HandBrakeCLI"


class TestParseProgressLine:
    """Tests for parse_progress_line function."""

    def test_parses_full_progress(self) -> None:
        """Test parsing full progress line."""
        line = "Encoding: task 1 of 1, 45.23 % (123.45 fps, avg 100.00 fps, ETA 00h10m30s)"
        progress = parse_progress_line(line)
        assert progress is not None
        assert progress.percent == 45.23
        assert progress.fps == 123.45
        assert progress.eta == "00h10m30s"

    def test_parses_minimal_progress(self) -> None:
        """Test parsing progress with only percentage."""
        line = "Encoding: task 1 of 1, 50 %"
        progress = parse_progress_line(line)
        assert progress is not None
        assert progress.percent == 50.0
        assert progress.fps is None
        assert progress.eta is None

    def test_returns_none_for_non_progress(self) -> None:
        """Test that non-progress lines return None."""
        line = "Loading input file..."
        progress = parse_progress_line(line)
        assert progress is None


class TestEncodeFile:
    """Tests for encode_file function."""

    @pytest.mark.asyncio
    async def test_input_file_not_found(self, tmp_path: Path) -> None:
        """Test error when input file doesn't exist."""
        input_path = tmp_path / "nonexistent.mkv"
        output_path = tmp_path / "output.mkv"

        with pytest.raises(InputFileError) as exc_info:
            await encode_file(input_path, output_path)

        assert exc_info.value.input_path == input_path
        assert "does not exist" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_input_path_is_directory(self, tmp_path: Path) -> None:
        """Test error when input path is a directory."""
        input_path = tmp_path / "somedir"
        input_path.mkdir()
        output_path = tmp_path / "output.mkv"

        with pytest.raises(InputFileError) as exc_info:
            await encode_file(input_path, output_path)

        assert "not a file" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_handbrake_not_found(self, tmp_path: Path) -> None:
        """Test error when HandBrakeCLI is not found."""
        input_path = tmp_path / "input.mkv"
        input_path.write_bytes(b"fake content")
        output_path = tmp_path / "output.mkv"

        with pytest.raises(HandBrakeNotFoundError) as exc_info:
            await encode_file(
                input_path,
                output_path,
                handbrake_cli="/nonexistent/HandBrakeCLI",
            )

        assert exc_info.value.path == "/nonexistent/HandBrakeCLI"

    @pytest.mark.asyncio
    async def test_encode_failure(self, tmp_path: Path) -> None:
        """Test error when encoding fails with non-zero exit code."""
        input_path = tmp_path / "input.mkv"
        input_path.write_bytes(b"fake content")
        output_path = tmp_path / "output.mkv"

        # Create a mock process that fails
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(
            side_effect=[
                b"Error: Invalid input\n",
                b"",
            ]
        )

        with patch(
            "dvdtoplex.handbrake.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            with pytest.raises(EncodeError) as exc_info:
                await encode_file(input_path, output_path)

            assert exc_info.value.exit_code == 1
            assert exc_info.value.input_path == input_path
            assert exc_info.value.output_path == output_path

    @pytest.mark.asyncio
    async def test_output_file_not_created(self, tmp_path: Path) -> None:
        """Test error when output file is not created after encoding."""
        input_path = tmp_path / "input.mkv"
        input_path.write_bytes(b"fake content")
        output_path = tmp_path / "output.mkv"

        # Create a mock process that succeeds but doesn't create output
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "dvdtoplex.handbrake.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            with pytest.raises(OutputFileError) as exc_info:
                await encode_file(input_path, output_path)

            assert exc_info.value.output_path == output_path
            assert "not created" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_output_file_empty(self, tmp_path: Path) -> None:
        """Test error when output file is empty."""
        input_path = tmp_path / "input.mkv"
        input_path.write_bytes(b"fake content")
        output_path = tmp_path / "output.mkv"

        # Create a mock process that succeeds
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        async def create_empty_output(*args, **kwargs):
            # Create empty output file
            output_path.write_bytes(b"")
            return mock_process

        with patch(
            "dvdtoplex.handbrake.asyncio.create_subprocess_exec",
            side_effect=create_empty_output,
        ):
            with pytest.raises(OutputFileError) as exc_info:
                await encode_file(input_path, output_path)

            assert "empty" in exc_info.value.details

    @pytest.mark.asyncio
    async def test_successful_encode(self, tmp_path: Path) -> None:
        """Test successful encoding."""
        input_path = tmp_path / "input.mkv"
        input_path.write_bytes(b"fake content")
        output_path = tmp_path / "output.mkv"

        progress_updates: list[EncodeProgress] = []

        def on_progress(p: EncodeProgress) -> None:
            progress_updates.append(p)

        # Create a mock process that succeeds
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(
            side_effect=[
                b"Encoding: task 1 of 1, 50 %\n",
                b"Encoding: task 1 of 1, 100 %\n",
                b"",
            ]
        )

        async def create_output_file(*args, **kwargs):
            # Create output file with content
            output_path.write_bytes(b"encoded content")
            return mock_process

        with patch(
            "dvdtoplex.handbrake.asyncio.create_subprocess_exec",
            side_effect=create_output_file,
        ):
            await encode_file(
                input_path, output_path, progress_callback=on_progress
            )

        # Verify progress was reported
        assert len(progress_updates) == 2
        assert progress_updates[0].percent == 50.0
        assert progress_updates[1].percent == 100.0
