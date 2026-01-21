# Parallel Agent Cleanup Design

## Context

142 parallel agents worked on the dvdtoplex codebase independently. The branches have been merged into `combined-work`, but tests fail due to interface mismatches between what tests expect and what implementations provide.

## Goal

Thorough cleanup: fix all test failures AND verify the application works end-to-end.

## Test Failure Categories

| Category | Count | Issue | Fix |
|----------|-------|-------|-----|
| Pytest-asyncio config | ~31 | Async fixtures missing `@pytest_asyncio.fixture` | Add proper decorators |
| Async test markers | ~21 | Tests missing `@pytest.mark.asyncio` | Add markers |
| Database API naming | ~3+ | Tests expect `initialize()`, code has `connect()` | Rename/alias + add `is_closed` |
| Drutil parsing | ~6 | Regex captures "Type:" instead of "Vendor:" | Fix regex pattern |

## Implementation Phases

### Phase 1: Test Infrastructure
1. Fix pytest-asyncio decorators in conftest.py and test files
2. Add `@pytest.mark.asyncio` to all async test methods
3. Update Database class: add `initialize()` method, `is_closed` property
4. Fix `parse_drutil_output()` regex for vendor field

### Phase 2: Integration Verification
1. Trace imports between modules for resolution issues
2. Verify function signatures match at module boundaries
3. Check web app can start and serve routes
4. Trace job lifecycle through services

### Phase 3: Smoke Test
1. TMDb API search test (verify credentials work)
2. Optional Pushover notification test
3. Start application and hit dashboard endpoint

## Out of Scope
- Actual DVD ripping (requires hardware)
- Performance optimization
- Load testing
- New feature development

## Success Criteria
- All 423 tests pass
- Application starts without errors
- Web dashboard accessible
- API integrations verified with real calls
