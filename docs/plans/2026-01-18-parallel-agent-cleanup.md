# Parallel Agent Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all test failures from parallel agent merge and verify end-to-end application functionality.

**Architecture:** Systematic fix of 4 test failure categories (pytest-asyncio config, async markers, Database API, drutil regex), followed by integration verification and API smoke tests.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, FastAPI, aiosqlite, httpx

---

## Phase 1: Test Infrastructure Fixes

### Task 1: Fix pytest-asyncio fixture decorators in conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Check current fixture definitions**

Run: `grep -n "async def" tests/conftest.py | head -20`

**Step 2: Add pytest_asyncio import and fix fixture decorators**

At top of file, ensure import exists:
```python
import pytest_asyncio
```

Change all async fixtures from:
```python
@pytest.fixture
async def some_fixture():
```

To:
```python
@pytest_asyncio.fixture
async def some_fixture():
```

**Step 3: Verify syntax is correct**

Run: `python -c "import tests.conftest"`
Expected: No errors

**Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "fix(tests): use pytest_asyncio.fixture for async fixtures in conftest"
```

---

### Task 2: Fix pytest-asyncio fixture decorators in test_database.py

**Files:**
- Modify: `tests/test_database.py`

**Step 1: Check current fixture definitions**

Run: `grep -n "@pytest.fixture" tests/test_database.py`

**Step 2: Add import and fix async fixtures**

Add at top:
```python
import pytest_asyncio
```

Change async fixtures from `@pytest.fixture` to `@pytest_asyncio.fixture`.

**Step 3: Add @pytest.mark.asyncio to all async test methods**

Find all `async def test_` methods and add `@pytest.mark.asyncio` decorator above each.

**Step 4: Verify syntax**

Run: `python -c "import tests.test_database"`
Expected: No errors

**Step 5: Commit**

```bash
git add tests/test_database.py
git commit -m "fix(tests): add pytest-asyncio markers to test_database.py"
```

---

### Task 3: Fix pytest-asyncio markers in test_shutdown.py

**Files:**
- Modify: `tests/test_shutdown.py`

**Step 1: Check for async tests without markers**

Run: `grep -n "async def test_" tests/test_shutdown.py`

**Step 2: Add @pytest.mark.asyncio to all async test methods**

Each `async def test_*` needs `@pytest.mark.asyncio` decorator.

**Step 3: Verify syntax**

Run: `python -c "import tests.test_shutdown"`
Expected: No errors

**Step 4: Commit**

```bash
git add tests/test_shutdown.py
git commit -m "fix(tests): add pytest-asyncio markers to test_shutdown.py"
```

---

### Task 4: Fix pytest-asyncio markers in remaining test files

**Files:**
- Modify: All test files with async tests

**Step 1: Find all async test methods across test files**

Run: `grep -rn "async def test_" tests/ --include="*.py"`

**Step 2: For each file with async tests, add markers**

Files likely needing fixes:
- `tests/test_drive_watcher.py`
- `tests/test_encode_queue.py`
- `tests/test_rip_queue.py`
- `tests/test_file_mover.py`
- `tests/test_identifier.py`
- `tests/test_main.py`
- `tests/test_graceful_shutdown.py`
- `tests/test_notifications.py`
- `tests/test_tmdb.py`
- `tests/test_web*.py`

Add `@pytest.mark.asyncio` above each `async def test_*` method.

**Step 3: Verify all imports work**

Run: `python -m pytest tests/ --collect-only 2>&1 | grep -E "(error|ERROR)" | head -10`
Expected: No import errors

**Step 4: Commit**

```bash
git add tests/
git commit -m "fix(tests): add pytest-asyncio markers to all async test methods"
```

---

### Task 5: Fix Database API - add initialize() method

**Files:**
- Modify: `src/dvdtoplex/database.py`

**Step 1: Read current Database class**

Run: `grep -n "async def" src/dvdtoplex/database.py | head -10`

**Step 2: Add initialize() as alias for connect()**

Find the `connect()` method and add `initialize()` that calls it:

```python
async def initialize(self) -> None:
    """Initialize the database (alias for connect)."""
    await self.connect()
```

Or rename `connect()` to `initialize()` if `connect()` isn't used elsewhere.

**Step 3: Verify syntax**

Run: `python -c "from dvdtoplex.database import Database; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add src/dvdtoplex/database.py
git commit -m "fix(database): add initialize() method for API consistency"
```

---

### Task 6: Fix Database API - add is_closed property

**Files:**
- Modify: `src/dvdtoplex/database.py`

**Step 1: Add is_closed property**

```python
@property
def is_closed(self) -> bool:
    """Check if database connection is closed."""
    return self._connection is None
```

**Step 2: Verify syntax**

Run: `python -c "from dvdtoplex.database import Database; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/dvdtoplex/database.py
git commit -m "fix(database): add is_closed property"
```

---

### Task 7: Fix drutil parsing regex

**Files:**
- Modify: `src/dvdtoplex/drives.py`

**Step 1: Find the incorrect regex**

Run: `grep -n "Type:" src/dvdtoplex/drives.py`

**Step 2: Change regex from Type to Vendor**

Change:
```python
vendor_match = re.search(r"Type:\s+(.+)", output)
```

To:
```python
vendor_match = re.search(r"Vendor:\s+(.+)", output)
```

**Step 3: Handle empty output edge case**

Ensure empty output returns `("", False, None)` instead of `(None, False, None)`:

```python
if not output or not output.strip():
    return ("", False, None)
```

**Step 4: Verify syntax**

Run: `python -c "from dvdtoplex.drives import parse_drutil_output; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add src/dvdtoplex/drives.py
git commit -m "fix(drives): correct drutil parsing regex for Vendor field"
```

---

### Task 8: Run tests and assess remaining failures

**Step 1: Run full test collection**

Run: `python -m pytest tests/ --collect-only 2>&1 | tail -5`
Expected: "collected 423 items" with no errors

**Step 2: Run tests with summary**

Run: `python -m pytest tests/ -q --tb=no -x 2>&1 | tail -20`

Note: `-x` stops at first failure to avoid hanging tests.

**Step 3: Document remaining failures**

If failures remain, note them for Phase 2.

**Step 4: Commit any additional fixes if needed**

---

## Phase 2: Integration Verification

### Task 9: Verify module imports resolve correctly

**Step 1: Test all main module imports**

Run:
```bash
python -c "
from dvdtoplex.config import Config, load_config
from dvdtoplex.database import Database
from dvdtoplex.drives import parse_drutil_output, get_drive_status
from dvdtoplex.makemkv import get_disc_info, rip_title
from dvdtoplex.handbrake import encode_file
from dvdtoplex.tmdb import TMDbClient
from dvdtoplex.notifications import Notifier
from dvdtoplex.main import Application, GracefulShutdown
print('All imports OK')
"
```
Expected: "All imports OK"

**Step 2: Test service imports**

Run:
```bash
python -c "
from dvdtoplex.services.drive_watcher import DriveWatcher
from dvdtoplex.services.rip_queue import RipQueue
from dvdtoplex.services.encode_queue import EncodeQueue
from dvdtoplex.services.identifier import IdentifierService
from dvdtoplex.services.file_mover import FileMover
print('All service imports OK')
"
```
Expected: "All service imports OK"

---

### Task 10: Verify web app can start

**Step 1: Test web app creation**

Run:
```bash
python -c "
from dvdtoplex.web.app import create_app
from dvdtoplex.config import Config
from dvdtoplex.database import Database
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    config = Config(workspace_dir=Path(tmpdir))
    # Just verify create_app doesn't crash
    print('Checking create_app signature...')
    import inspect
    sig = inspect.signature(create_app)
    print(f'create_app params: {list(sig.parameters.keys())}')
"
```

Note the parameters - we'll need them for the smoke test.

---

### Task 11: Verify Application can initialize

**Step 1: Test Application initialization**

Run:
```bash
python -c "
import asyncio
from dvdtoplex.config import Config
from dvdtoplex.main import Application
from pathlib import Path
import tempfile

async def test():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(workspace_dir=Path(tmpdir))
        app = Application(config)
        await app.initialize()
        print(f'Workspace exists: {config.workspace_dir.exists()}')
        print(f'Staging exists: {config.staging_dir.exists()}')
        print(f'Database initialized: {app.database is not None}')
        await app.shutdown()
        print('Application shutdown OK')

asyncio.run(test())
"
```
Expected: All True, "Application shutdown OK"

---

## Phase 3: Smoke Tests

### Task 12: Test TMDb API integration

**Step 1: Load credentials and test search**

Run:
```bash
python -c "
import asyncio
from dvdtoplex.config import load_config
from dvdtoplex.tmdb import TMDbClient

async def test():
    config = load_config()
    if not config.tmdb_api_token:
        print('SKIP: No TMDb token configured')
        return

    async with TMDbClient(config.tmdb_api_token) as client:
        results = await client.search_movie('The Matrix')
        print(f'Found {len(results)} results for \"The Matrix\"')
        if results:
            print(f'Top result: {results[0].title} ({results[0].year})')

asyncio.run(test())
"
```
Expected: Results found, "The Matrix (1999)"

---

### Task 13: Test Pushover API integration (optional)

**Step 1: Send test notification**

Run:
```bash
python -c "
import asyncio
from dvdtoplex.config import load_config
from dvdtoplex.notifications import Notifier

async def test():
    config = load_config()
    notifier = Notifier(config.pushover_user_key, config.pushover_api_token)

    if not notifier.is_configured:
        print('SKIP: Pushover not configured')
        return

    result = await notifier.send(
        title='DVD-to-Plex Test',
        message='Integration test - system is working!',
        priority=-1  # Low priority for test
    )
    print(f'Notification sent: {result}')

asyncio.run(test())
"
```
Expected: "Notification sent: True"

---

### Task 14: Final test run and summary

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short 2>&1 | tee test_results.txt | tail -50`

**Step 2: Generate summary**

Run: `grep -E "^(PASSED|FAILED|ERROR|tests/)" test_results.txt | tail -30`

**Step 3: Commit final state**

```bash
git add -A
git commit -m "fix: complete parallel agent cleanup - all tests passing"
```

---

## Success Criteria

- [ ] All 423 tests collected without errors
- [ ] Test pass rate > 95% (some may need real hardware)
- [ ] Application initializes and shuts down cleanly
- [ ] Web app can be created without errors
- [ ] TMDb API integration verified
- [ ] Pushover integration verified (if configured)
