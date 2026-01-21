"""Tests for archive job endpoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from dvdtoplex.web.app import create_app
from dvdtoplex.database import JobStatus


class TestArchiveEndpoint:
    """Tests for POST /api/jobs/{job_id}/archive endpoint."""

    @pytest.mark.asyncio
    async def test_archive_job_success(self):
        """Test archive endpoint marks job as ARCHIVED."""
        mock_db = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.status = JobStatus.COMPLETE
        mock_db.get_job.return_value = mock_job
        mock_db.update_job_status.return_value = None

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/1/archive")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "archived"
        mock_db.update_job_status.assert_called_once_with(1, JobStatus.ARCHIVED)

    @pytest.mark.asyncio
    async def test_archive_failed_job_success(self):
        """Test archive works on failed jobs."""
        mock_db = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.status = JobStatus.FAILED
        mock_db.get_job.return_value = mock_job
        mock_db.update_job_status.return_value = None

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/1/archive")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_archive_job_only_complete_or_failed(self):
        """Test archive only works on COMPLETE or FAILED jobs."""
        mock_db = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.status = JobStatus.ENCODING
        mock_db.get_job.return_value = mock_job

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/1/archive")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_archive_job_not_found(self):
        """Test archive returns 404 when job not found."""
        mock_db = AsyncMock()
        mock_db.get_job.return_value = None

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/999/archive")

        assert response.status_code == 404
