"""Tests to verify all module imports work correctly."""


def test_config_imports() -> None:
    """Verify config module imports."""
    from dvdtoplex.config import Config, load_config

    assert Config is not None
    assert load_config is not None


def test_database_imports() -> None:
    """Verify database module imports."""
    from dvdtoplex.database import Database

    assert Database is not None


def test_drives_imports() -> None:
    """Verify drives module imports."""
    from dvdtoplex.drives import get_drive_status, parse_drutil_output

    assert parse_drutil_output is not None
    assert get_drive_status is not None


def test_makemkv_imports() -> None:
    """Verify makemkv module imports."""
    from dvdtoplex.makemkv import get_disc_info, rip_title

    assert rip_title is not None
    assert get_disc_info is not None


def test_handbrake_imports() -> None:
    """Verify handbrake module imports."""
    from dvdtoplex.handbrake import encode_file

    assert encode_file is not None


def test_tmdb_imports() -> None:
    """Verify tmdb module imports."""
    from dvdtoplex.tmdb import TMDbClient

    assert TMDbClient is not None


def test_notifications_imports() -> None:
    """Verify notifications module imports."""
    from dvdtoplex.notifications import Notifier

    assert Notifier is not None


def test_main_imports() -> None:
    """Verify main module imports."""
    from dvdtoplex.main import Application, GracefulShutdown

    assert Application is not None
    assert GracefulShutdown is not None


def test_drive_watcher_imports() -> None:
    """Verify drive_watcher service imports."""
    from dvdtoplex.services.drive_watcher import DriveWatcher

    assert DriveWatcher is not None


def test_rip_queue_imports() -> None:
    """Verify rip_queue service imports."""
    from dvdtoplex.services.rip_queue import RipQueue

    assert RipQueue is not None


def test_encode_queue_imports() -> None:
    """Verify encode_queue service imports."""
    from dvdtoplex.services.encode_queue import EncodeQueue

    assert EncodeQueue is not None


def test_identifier_imports() -> None:
    """Verify identifier service imports."""
    from dvdtoplex.services.identifier import IdentifierService

    assert IdentifierService is not None


def test_file_mover_imports() -> None:
    """Verify file_mover service imports."""
    from dvdtoplex.services.file_mover import FileMover

    assert FileMover is not None


def test_all_main_imports() -> None:
    """Test all main imports in one go - mirrors PRD acceptance criteria."""
    from dvdtoplex.config import Config, load_config
    from dvdtoplex.database import Database
    from dvdtoplex.drives import get_drive_status, parse_drutil_output
    from dvdtoplex.handbrake import encode_file
    from dvdtoplex.main import Application, GracefulShutdown
    from dvdtoplex.makemkv import get_disc_info, rip_title
    from dvdtoplex.notifications import Notifier
    from dvdtoplex.tmdb import TMDbClient

    # All should be non-None
    all_imports = [
        Config,
        load_config,
        Database,
        parse_drutil_output,
        get_drive_status,
        get_disc_info,
        rip_title,
        encode_file,
        TMDbClient,
        Notifier,
        Application,
        GracefulShutdown,
    ]
    assert all(x is not None for x in all_imports)
    print("All imports OK")


def test_all_service_imports() -> None:
    """Test all service imports in one go - mirrors PRD acceptance criteria."""
    from dvdtoplex.services.drive_watcher import DriveWatcher
    from dvdtoplex.services.encode_queue import EncodeQueue
    from dvdtoplex.services.file_mover import FileMover
    from dvdtoplex.services.identifier import IdentifierService
    from dvdtoplex.services.rip_queue import RipQueue

    # All should be non-None
    all_imports = [
        DriveWatcher,
        RipQueue,
        EncodeQueue,
        IdentifierService,
        FileMover,
    ]
    assert all(x is not None for x in all_imports)
    print("All service imports OK")
