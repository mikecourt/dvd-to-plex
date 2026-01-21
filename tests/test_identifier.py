"""Tests for the identifier service."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from dvdtoplex.config import Config
from dvdtoplex.database import ContentType, Database, Job, JobStatus
from dvdtoplex.services.identifier import (
    IdentificationResult,
    IdentifierService,
    calculate_confidence,
    calculate_popularity_score,
    calculate_title_similarity,
)
from dvdtoplex.tmdb import MovieMatch, TMDbClient, TVMatch


class TestCalculateTitleSimilarity:
    """Tests for calculate_title_similarity function."""

    def test_exact_match(self) -> None:
        """Exact matches should return 1.0."""
        assert calculate_title_similarity("The Matrix", "The Matrix") == 1.0

    def test_case_insensitive(self) -> None:
        """Matching should be case-insensitive."""
        assert calculate_title_similarity("THE MATRIX", "The Matrix") == 1.0

    def test_special_characters_ignored(self) -> None:
        """Special characters should be ignored."""
        assert calculate_title_similarity("Schindler's List", "Schindlers List") == 1.0

    def test_partial_match(self) -> None:
        """Partial matches should return partial scores."""
        score = calculate_title_similarity("Matrix", "The Matrix")
        assert 0.5 < score < 1.0

    def test_no_match(self) -> None:
        """Non-matching titles should return low scores."""
        score = calculate_title_similarity("Inception", "The Godfather")
        assert score < 0.5

    def test_empty_strings(self) -> None:
        """Empty strings should return 1.0 (both empty = same)."""
        assert calculate_title_similarity("", "") == 1.0


class TestCalculatePopularityScore:
    """Tests for calculate_popularity_score function."""

    def test_zero_popularity(self) -> None:
        """Zero popularity should return 0.0."""
        assert calculate_popularity_score(0.0) == 0.0

    def test_max_popularity(self) -> None:
        """Max popularity should return 1.0."""
        assert calculate_popularity_score(100.0) == 1.0

    def test_over_max_popularity(self) -> None:
        """Over max should still return 1.0 (capped)."""
        assert calculate_popularity_score(150.0) == 1.0

    def test_mid_popularity(self) -> None:
        """Mid-range popularity should return 0.5."""
        assert calculate_popularity_score(50.0) == 0.5


class TestCalculateConfidence:
    """Tests for calculate_confidence function."""

    def test_perfect_match_high_popularity(self) -> None:
        """Perfect match with high popularity should be near 1.0."""
        confidence = calculate_confidence(
            query="The Matrix",
            result_title="The Matrix",
            popularity=100.0,
            is_first_result=True,
        )
        assert confidence > 0.95

    def test_perfect_match_low_popularity(self) -> None:
        """Perfect match with low popularity should still be decent."""
        confidence = calculate_confidence(
            query="The Matrix",
            result_title="The Matrix",
            popularity=0.0,
            is_first_result=True,
        )
        # 0.60 (title) + 0.0 (popularity) + 0.15 (rank) = 0.75
        assert 0.70 < confidence < 0.80

    def test_not_first_result_penalty(self) -> None:
        """Not being first result should reduce confidence."""
        first_conf = calculate_confidence(
            query="Matrix",
            result_title="The Matrix",
            popularity=50.0,
            is_first_result=True,
        )
        other_conf = calculate_confidence(
            query="Matrix",
            result_title="The Matrix",
            popularity=50.0,
            is_first_result=False,
        )
        assert first_conf > other_conf

    def test_poor_match(self) -> None:
        """Poor title match should give low confidence."""
        confidence = calculate_confidence(
            query="RANDOM_DISC_123",
            result_title="The Shawshank Redemption",
            popularity=100.0,
            is_first_result=True,
        )
        assert confidence < 0.6


class TestIdentificationResult:
    """Tests for IdentificationResult dataclass."""

    def test_create_movie_result(self) -> None:
        """Creating a movie identification result."""
        result = IdentificationResult(
            content_type=ContentType.MOVIE,
            title="The Matrix",
            year=1999,
            tmdb_id=603,
            confidence=0.95,
            needs_review=False,
            alternatives=[],
        )
        assert result.content_type == ContentType.MOVIE
        assert result.title == "The Matrix"
        assert result.year == 1999
        assert result.tmdb_id == 603
        assert result.confidence == 0.95
        assert not result.needs_review
        assert result.alternatives == []

    def test_create_result_with_alternatives(self) -> None:
        """Creating result with alternatives."""
        alt = MovieMatch(
            tmdb_id=604,
            title="The Matrix Reloaded",
            year=2003,
            overview="Neo and friends continue the fight.",
            poster_path="/path.jpg",
            popularity=80.0,
        )
        result = IdentificationResult(
            content_type=ContentType.MOVIE,
            title="The Matrix",
            year=1999,
            tmdb_id=603,
            confidence=0.95,
            needs_review=False,
            alternatives=[alt],
        )
        assert len(result.alternatives) == 1
        assert result.alternatives[0].tmdb_id == 604


class TestIdentifierService:
    """Tests for IdentifierService class."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock(spec=Database)
        db.get_jobs_by_status = AsyncMock(return_value=[])
        db.update_job_status = AsyncMock()
        db.update_job_identification = AsyncMock()
        return db

    @pytest.fixture
    def mock_config(self) -> Config:
        """Create a test config."""
        return Config(
            tmdb_api_token="test_token",
            auto_approve_threshold=0.85,
        )

    @pytest.fixture
    def mock_tmdb(self) -> MagicMock:
        """Create a mock TMDb client."""
        tmdb = MagicMock(spec=TMDbClient)
        tmdb.search_movie = AsyncMock(return_value=[])
        tmdb.search_tv = AsyncMock(return_value=[])
        tmdb.get_movie_details = AsyncMock(return_value=None)
        tmdb.close = AsyncMock()
        return tmdb

    @pytest.fixture
    def service(
        self, mock_db: MagicMock, mock_config: Config, mock_tmdb: MagicMock
    ) -> IdentifierService:
        """Create an identifier service with mocks."""
        return IdentifierService(
            db=mock_db,
            config=mock_config,
            tmdb_client=mock_tmdb,
        )

    @pytest.mark.asyncio
    async def test_identify_movie_high_confidence(
        self, service: IdentifierService, mock_tmdb: MagicMock
    ) -> None:
        """High confidence movie match should not need review."""
        mock_tmdb.search_movie.return_value = [
            MovieMatch(
                tmdb_id=603,
                title="The Matrix",
                year=1999,
                overview="A computer hacker learns about the true nature of reality.",
                poster_path="/matrix.jpg",
                popularity=100.0,
            )
        ]

        result = await service.identify("THE_MATRIX_DVD")

        assert result.content_type == ContentType.MOVIE
        assert result.title == "The Matrix"
        assert result.year == 1999
        assert result.tmdb_id == 603
        assert result.confidence > 0.85
        assert not result.needs_review

    @pytest.mark.asyncio
    async def test_identify_movie_low_confidence(
        self, service: IdentifierService, mock_tmdb: MagicMock
    ) -> None:
        """Low confidence match should need review."""
        mock_tmdb.search_movie.return_value = [
            MovieMatch(
                tmdb_id=123,
                title="Some Random Movie",
                year=2020,
                overview="An obscure film.",
                poster_path=None,
                popularity=1.0,
            )
        ]
        mock_tmdb.search_tv.return_value = []

        result = await service.identify("COMPLETELY_DIFFERENT_LABEL")

        assert result.needs_review
        assert result.confidence < 0.85

    @pytest.mark.asyncio
    async def test_identify_no_results(
        self, service: IdentifierService, mock_tmdb: MagicMock
    ) -> None:
        """No TMDb results should return unknown with review needed."""
        mock_tmdb.search_movie.return_value = []
        mock_tmdb.search_tv.return_value = []

        result = await service.identify("VERY_OBSCURE_DISC")

        assert result.content_type == ContentType.UNKNOWN
        assert result.tmdb_id is None
        assert result.confidence == 0.0
        assert result.needs_review

    @pytest.mark.asyncio
    async def test_identify_tv_show(
        self, service: IdentifierService, mock_tmdb: MagicMock
    ) -> None:
        """TV show should be identified if it matches better than movies."""
        mock_tmdb.search_movie.return_value = [
            MovieMatch(
                tmdb_id=999,
                title="Breaking Point",
                year=2010,
                overview="Some unrelated movie.",
                poster_path=None,
                popularity=5.0,
            )
        ]
        mock_tmdb.search_tv.return_value = [
            TVMatch(
                tmdb_id=1396,
                name="Breaking Bad",
                year=2008,
                overview="A high school chemistry teacher turns to meth production.",
                poster_path="/bb.jpg",
                popularity=150.0,
            )
        ]

        result = await service.identify("BREAKING_BAD_S1")

        assert result.content_type == ContentType.TV_SEASON
        assert result.title == "Breaking Bad"
        assert result.tmdb_id == 1396

    @pytest.mark.asyncio
    async def test_identify_includes_alternatives(
        self, service: IdentifierService, mock_tmdb: MagicMock
    ) -> None:
        """Result should include alternative matches."""
        mock_tmdb.search_movie.return_value = [
            MovieMatch(
                tmdb_id=603,
                title="The Matrix",
                year=1999,
                overview="First movie.",
                poster_path="/m1.jpg",
                popularity=100.0,
            ),
            MovieMatch(
                tmdb_id=604,
                title="The Matrix Reloaded",
                year=2003,
                overview="Second movie.",
                poster_path="/m2.jpg",
                popularity=80.0,
            ),
            MovieMatch(
                tmdb_id=605,
                title="The Matrix Revolutions",
                year=2003,
                overview="Third movie.",
                poster_path="/m3.jpg",
                popularity=70.0,
            ),
        ]
        mock_tmdb.search_tv.return_value = []

        result = await service.identify("THE_MATRIX")

        assert len(result.alternatives) >= 2
        assert result.alternatives[0].tmdb_id == 604
        assert result.alternatives[1].tmdb_id == 605

    @pytest.mark.asyncio
    async def test_identify_and_update_job(
        self, service: IdentifierService, mock_db: MagicMock, mock_tmdb: MagicMock
    ) -> None:
        """Manual identification should update job and set to MOVING."""
        from dvdtoplex.tmdb import MovieDetails
        mock_tmdb.get_movie_details.return_value = MovieDetails(
            tmdb_id=603,
            title="The Matrix",
            year=1999,
            overview="Neo wakes up.",
            poster_path="/matrix.jpg",
            popularity=100.0,
            runtime=136,
            genres=["Action", "Sci-Fi"],
            tagline="Free your mind.",
        )

        await service.identify_and_update_job(
            job_id=1,
            title="The Matrix",
            year=1999,
            tmdb_id=603,
        )

        mock_db.update_job_identification.assert_called_once_with(
            job_id=1,
            content_type=ContentType.MOVIE,
            title="The Matrix",
            year=1999,
            tmdb_id=603,
            confidence=1.0,
            poster_path="/matrix.jpg",
        )
        mock_db.update_job_status.assert_called_once_with(1, JobStatus.MOVING)

    @pytest.mark.asyncio
    async def test_start_stop_service(self, service: IdentifierService) -> None:
        """Service should start and stop cleanly."""
        await service.start()
        assert service._running

        await service.stop()
        assert not service._running


class TestIdentifierServiceJobProcessing:
    """Tests for job processing in IdentifierService."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database with a job."""
        db = MagicMock(spec=Database)
        db.get_jobs_by_status = AsyncMock()
        db.update_job_status = AsyncMock()
        db.update_job_identification = AsyncMock()
        return db

    @pytest.fixture
    def sample_job(self) -> Job:
        """Create a sample encoded job."""
        from datetime import datetime
        return Job(
            id=1,
            drive_id="/dev/disk2",
            disc_label="THE_MATRIX_WS",
            content_type=ContentType.UNKNOWN,
            status=JobStatus.ENCODED,
            identified_title=None,
            identified_year=None,
            tmdb_id=None,
            confidence=None,
            poster_path=None,
            rip_path="/workspace/staging/job_1/movie.mkv",
            encode_path="/workspace/encoding/job_1/movie.mkv",
            final_path=None,
            error_message=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    @pytest.mark.asyncio
    async def test_process_encoded_job_auto_approve(
        self, mock_db: MagicMock, sample_job: Job
    ) -> None:
        """Job with high confidence should transition to MOVING."""
        mock_db.get_jobs_by_status.return_value = [sample_job]

        mock_tmdb = MagicMock(spec=TMDbClient)
        mock_tmdb.search_movie = AsyncMock(return_value=[
            MovieMatch(
                tmdb_id=603,
                title="The Matrix",
                year=1999,
                overview="Neo discovers the truth.",
                poster_path="/m.jpg",
                popularity=100.0,
            )
        ])
        mock_tmdb.search_tv = AsyncMock(return_value=[])
        mock_tmdb.close = AsyncMock()

        config = Config(tmdb_api_token="test", auto_approve_threshold=0.85)
        service = IdentifierService(db=mock_db, config=config, tmdb_client=mock_tmdb)

        await service._process_encoded_jobs()

        # Should have been marked as IDENTIFYING first
        calls = mock_db.update_job_status.call_args_list
        assert any(call[0][1] == JobStatus.IDENTIFYING for call in calls)

        # Should end up as MOVING (auto-approved)
        assert any(call[0][1] == JobStatus.MOVING for call in calls)

    @pytest.mark.asyncio
    async def test_process_encoded_job_needs_review(
        self, mock_db: MagicMock, sample_job: Job
    ) -> None:
        """Job with low confidence should transition to REVIEW."""
        sample_job.disc_label = "RANDOM_OBSCURE_DISC"
        mock_db.get_jobs_by_status.return_value = [sample_job]

        mock_tmdb = MagicMock(spec=TMDbClient)
        mock_tmdb.search_movie = AsyncMock(return_value=[
            MovieMatch(
                tmdb_id=999,
                title="Something Else Entirely",
                year=2020,
                overview="Unrelated movie.",
                poster_path=None,
                popularity=1.0,
            )
        ])
        mock_tmdb.search_tv = AsyncMock(return_value=[])
        mock_tmdb.close = AsyncMock()

        config = Config(tmdb_api_token="test", auto_approve_threshold=0.85)
        service = IdentifierService(db=mock_db, config=config, tmdb_client=mock_tmdb)

        await service._process_encoded_jobs()

        # Should end up in REVIEW
        calls = mock_db.update_job_status.call_args_list
        assert any(call[0][1] == JobStatus.REVIEW for call in calls)

    @pytest.mark.asyncio
    async def test_process_job_error_handling(
        self, mock_db: MagicMock, sample_job: Job
    ) -> None:
        """Job processing errors should mark job as FAILED."""
        mock_db.get_jobs_by_status.return_value = [sample_job]

        mock_tmdb = MagicMock(spec=TMDbClient)
        mock_tmdb.search_movie = AsyncMock(side_effect=Exception("API Error"))
        mock_tmdb.close = AsyncMock()

        config = Config(tmdb_api_token="test", auto_approve_threshold=0.85)
        service = IdentifierService(db=mock_db, config=config, tmdb_client=mock_tmdb)

        await service._process_encoded_jobs()

        # Job should be marked as FAILED with error message
        calls = mock_db.update_job_status.call_args_list
        failed_call = next(
            (call for call in calls if call[0][1] == JobStatus.FAILED), None
        )
        assert failed_call is not None
        assert "API Error" in failed_call[1].get("error_message", "")
