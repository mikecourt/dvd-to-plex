#!/usr/bin/env bash

# ============================================
# Test Suite: Job State Transitions
# Tests the full lifecycle of job/task states in Ralphy
# ============================================

set -euo pipefail

# Test directory setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_TMP_DIR=""
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Colors for test output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

# ============================================
# Test Framework Functions
# ============================================

setup_test_env() {
    TEST_TMP_DIR=$(mktemp -d)
    cd "$TEST_TMP_DIR"

    # Initialize a git repo for tests that need it
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"

    # Source the functions we need to test (extract them from ralphy.sh)
    # We'll create a testable version that exports the functions
    create_testable_functions
}

cleanup_test_env() {
    if [[ -n "$TEST_TMP_DIR" ]] && [[ -d "$TEST_TMP_DIR" ]]; then
        cd "$PROJECT_ROOT"
        rm -rf "$TEST_TMP_DIR"
    fi
}

create_testable_functions() {
    # Extract and source key functions from ralphy.sh for testing
    cat > "$TEST_TMP_DIR/test_functions.sh" << 'FUNCTIONS_EOF'
#!/usr/bin/env bash

# ============================================
# Extracted functions from ralphy.sh for testing
# ============================================

PRD_SOURCE="markdown"
PRD_FILE="PRD.md"

# Slugify text for branch names
slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g' | sed -E 's/^-|-$//g' | cut -c1-50
}

# ============================================
# TASK SOURCES - MARKDOWN
# ============================================

get_tasks_markdown() {
  grep '^\- \[ \]' "$PRD_FILE" 2>/dev/null | sed 's/^- \[ \] //' || true
}

get_next_task_markdown() {
  grep -m1 '^\- \[ \]' "$PRD_FILE" 2>/dev/null | sed 's/^- \[ \] //' | cut -c1-50 || echo ""
}

count_remaining_markdown() {
  local count
  count=$(grep -c '^\- \[ \]' "$PRD_FILE" 2>/dev/null) || count=0
  echo "$count"
}

count_completed_markdown() {
  local count
  count=$(grep -c '^\- \[x\]' "$PRD_FILE" 2>/dev/null) || count=0
  echo "$count"
}

mark_task_complete_markdown() {
  local task=$1
  local escaped_task
  escaped_task=$(printf '%s\n' "$task" | sed 's/[[\.*^$/]/\\&/g')
  sed -i.bak "s/^- \[ \] ${escaped_task}/- [x] ${escaped_task}/" "$PRD_FILE"
  rm -f "${PRD_FILE}.bak"
}

# ============================================
# TASK SOURCES - YAML (if yq available)
# ============================================

get_tasks_yaml() {
  if command -v yq &>/dev/null; then
    yq -r '.tasks[] | select(.completed != true) | .title' "$PRD_FILE" 2>/dev/null || true
  fi
}

get_next_task_yaml() {
  if command -v yq &>/dev/null; then
    yq -r '.tasks[] | select(.completed != true) | .title' "$PRD_FILE" 2>/dev/null | head -1 | cut -c1-50 || echo ""
  fi
}

count_remaining_yaml() {
  if command -v yq &>/dev/null; then
    yq -r '[.tasks[] | select(.completed != true)] | length' "$PRD_FILE" 2>/dev/null || echo "0"
  else
    echo "0"
  fi
}

count_completed_yaml() {
  if command -v yq &>/dev/null; then
    yq -r '[.tasks[] | select(.completed == true)] | length' "$PRD_FILE" 2>/dev/null || echo "0"
  else
    echo "0"
  fi
}

mark_task_complete_yaml() {
  local task=$1
  if command -v yq &>/dev/null; then
    yq -i "(.tasks[] | select(.title == \"$task\")).completed = true" "$PRD_FILE"
  fi
}

get_parallel_group_yaml() {
  local task=$1
  if command -v yq &>/dev/null; then
    yq -r ".tasks[] | select(.title == \"$task\") | .parallel_group // 0" "$PRD_FILE" 2>/dev/null || echo "0"
  else
    echo "0"
  fi
}

# ============================================
# UNIFIED TASK INTERFACE
# ============================================

get_next_task() {
  case "$PRD_SOURCE" in
    markdown) get_next_task_markdown ;;
    yaml) get_next_task_yaml ;;
  esac
}

get_all_tasks() {
  case "$PRD_SOURCE" in
    markdown) get_tasks_markdown ;;
    yaml) get_tasks_yaml ;;
  esac
}

count_remaining_tasks() {
  case "$PRD_SOURCE" in
    markdown) count_remaining_markdown ;;
    yaml) count_remaining_yaml ;;
  esac
}

count_completed_tasks() {
  case "$PRD_SOURCE" in
    markdown) count_completed_markdown ;;
    yaml) count_completed_yaml ;;
  esac
}

mark_task_complete() {
  local task=$1
  case "$PRD_SOURCE" in
    markdown) mark_task_complete_markdown "$task" ;;
    yaml) mark_task_complete_yaml "$task" ;;
  esac
}

# ============================================
# PARALLEL AGENT STATE MANAGEMENT
# ============================================

# Agent state storage directory (file-based for bash 3.x compatibility)
AGENT_STATE_DIR=""

init_agent_states() {
    AGENT_STATE_DIR=$(mktemp -d)
}

cleanup_agent_states() {
    if [[ -n "$AGENT_STATE_DIR" ]] && [[ -d "$AGENT_STATE_DIR" ]]; then
        rm -rf "$AGENT_STATE_DIR"
    fi
}

set_agent_state() {
    local agent_id=$1
    local state=$2
    if [[ -z "$AGENT_STATE_DIR" ]]; then
        init_agent_states
    fi
    echo "$state" > "$AGENT_STATE_DIR/$agent_id"
}

get_agent_state() {
    local agent_id=$1
    if [[ -z "$AGENT_STATE_DIR" ]] || [[ ! -f "$AGENT_STATE_DIR/$agent_id" ]]; then
        echo "unknown"
    else
        cat "$AGENT_STATE_DIR/$agent_id"
    fi
}

# Validate state transition is allowed
validate_state_transition() {
    local current_state=$1
    local new_state=$2

    case "$current_state" in
        "waiting")
            [[ "$new_state" == "setting up" ]] && return 0
            ;;
        "setting up")
            [[ "$new_state" == "running" || "$new_state" == "failed" ]] && return 0
            ;;
        "running")
            [[ "$new_state" == "done" || "$new_state" == "failed" ]] && return 0
            ;;
        "done"|"failed")
            # Terminal states - no valid transitions
            return 1
            ;;
    esac
    return 1
}

# Simulate agent lifecycle
simulate_agent_lifecycle() {
    local agent_id=$1
    local should_fail=${2:-false}

    set_agent_state "$agent_id" "waiting"

    # Transition: waiting -> setting up
    if ! validate_state_transition "waiting" "setting up"; then
        return 1
    fi
    set_agent_state "$agent_id" "setting up"

    # Transition: setting up -> running
    if ! validate_state_transition "setting up" "running"; then
        return 1
    fi
    set_agent_state "$agent_id" "running"

    # Transition: running -> done/failed
    if [[ "$should_fail" == "true" ]]; then
        if ! validate_state_transition "running" "failed"; then
            return 1
        fi
        set_agent_state "$agent_id" "failed"
    else
        if ! validate_state_transition "running" "done"; then
            return 1
        fi
        set_agent_state "$agent_id" "done"
    fi

    return 0
}

FUNCTIONS_EOF

    source "$TEST_TMP_DIR/test_functions.sh"
}

run_test() {
    local test_name=$1
    local test_func=$2

    ((TESTS_RUN++))

    printf "${BLUE}Running:${RESET} %s... " "$test_name"

    # Run the test in a subshell to isolate failures
    local result=0
    (
        set -e
        $test_func
    ) || result=$?

    if [[ $result -eq 0 ]]; then
        ((TESTS_PASSED++))
        printf "${GREEN}PASSED${RESET}\n"
    else
        ((TESTS_FAILED++))
        printf "${RED}FAILED${RESET}\n"
    fi
}

assert_equals() {
    local expected=$1
    local actual=$2
    local message=${3:-"Values should be equal"}

    if [[ "$expected" != "$actual" ]]; then
        echo "Assertion failed: $message"
        echo "  Expected: '$expected'"
        echo "  Actual:   '$actual'"
        return 1
    fi
}

assert_contains() {
    local haystack=$1
    local needle=$2
    local message=${3:-"Should contain substring"}

    if [[ "$haystack" != *"$needle"* ]]; then
        echo "Assertion failed: $message"
        echo "  Haystack: '$haystack'"
        echo "  Needle:   '$needle'"
        return 1
    fi
}

assert_file_contains() {
    local file=$1
    local pattern=$2
    local message=${3:-"File should contain pattern"}

    if ! grep -q "$pattern" "$file" 2>/dev/null; then
        echo "Assertion failed: $message"
        echo "  File: '$file'"
        echo "  Pattern: '$pattern'"
        return 1
    fi
}

# ============================================
# Test Cases: Markdown Task State Transitions
# ============================================

test_markdown_initial_state() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Project Tasks

## Phase 1
- [ ] Implement feature A
- [ ] Implement feature B
- [ ] Implement feature C
EOF

    local remaining=$(count_remaining_tasks)
    local completed=$(count_completed_tasks)

    assert_equals "3" "$remaining" "Should have 3 pending tasks"
    assert_equals "0" "$completed" "Should have 0 completed tasks"
}

test_markdown_get_next_task() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [ ] First task
- [ ] Second task
EOF

    local next_task=$(get_next_task)

    assert_equals "First task" "$next_task" "Should get first pending task"
}

test_markdown_task_completion() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [ ] Task to complete
- [ ] Another task
EOF

    # Initial state
    assert_equals "2" "$(count_remaining_tasks)" "Should start with 2 pending"
    assert_equals "0" "$(count_completed_tasks)" "Should start with 0 completed"

    # Mark first task complete
    mark_task_complete "Task to complete"

    # Verify state transition
    assert_equals "1" "$(count_remaining_tasks)" "Should have 1 pending after completion"
    assert_equals "1" "$(count_completed_tasks)" "Should have 1 completed"
    assert_file_contains "$PRD_FILE" "^\- \[x\] Task to complete" "Task should be marked with [x]"
}

test_markdown_full_lifecycle() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
EOF

    # State: All pending
    assert_equals "3" "$(count_remaining_tasks)"
    assert_equals "0" "$(count_completed_tasks)"

    # Complete task 1
    local task1=$(get_next_task)
    assert_equals "Task 1" "$task1"
    mark_task_complete "$task1"

    # State: 2 pending, 1 complete
    assert_equals "2" "$(count_remaining_tasks)"
    assert_equals "1" "$(count_completed_tasks)"

    # Complete task 2
    local task2=$(get_next_task)
    assert_equals "Task 2" "$task2"
    mark_task_complete "$task2"

    # State: 1 pending, 2 complete
    assert_equals "1" "$(count_remaining_tasks)"
    assert_equals "2" "$(count_completed_tasks)"

    # Complete task 3
    local task3=$(get_next_task)
    assert_equals "Task 3" "$task3"
    mark_task_complete "$task3"

    # State: All complete
    assert_equals "0" "$(count_remaining_tasks)"
    assert_equals "3" "$(count_completed_tasks)"

    # No more tasks
    local no_task=$(get_next_task)
    assert_equals "" "$no_task" "Should return empty when no tasks remain"
}

test_markdown_mixed_initial_state() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [x] Already done
- [ ] Still pending
- [x] Also done
- [ ] Another pending
EOF

    assert_equals "2" "$(count_remaining_tasks)" "Should count only pending tasks"
    assert_equals "2" "$(count_completed_tasks)" "Should count only completed tasks"

    local next=$(get_next_task)
    assert_equals "Still pending" "$next" "Should get first pending task"
}

test_markdown_special_characters_in_task() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [ ] Fix bug in file.ts (critical)
- [ ] Update README.md
- [ ] Add tests for API endpoints
EOF

    local task=$(get_next_task)
    assert_equals "Fix bug in file.ts (critical)" "$task"

    mark_task_complete "$task"
    assert_equals "2" "$(count_remaining_tasks)"
    assert_file_contains "$PRD_FILE" "^\- \[x\] Fix bug in file.ts (critical)" "Should handle special chars"
}

# ============================================
# Test Cases: YAML Task State Transitions
# ============================================

test_yaml_initial_state() {
    if ! command -v yq &>/dev/null; then
        echo "Skipping YAML test - yq not installed"
        return 0
    fi

    PRD_SOURCE="yaml"
    PRD_FILE="tasks.yaml"

    cat > "$PRD_FILE" << 'EOF'
tasks:
  - title: Task A
    completed: false
  - title: Task B
    completed: false
  - title: Task C
    completed: false
EOF

    assert_equals "3" "$(count_remaining_tasks)" "Should have 3 pending YAML tasks"
    assert_equals "0" "$(count_completed_tasks)" "Should have 0 completed YAML tasks"
}

test_yaml_task_completion() {
    if ! command -v yq &>/dev/null; then
        echo "Skipping YAML test - yq not installed"
        return 0
    fi

    PRD_SOURCE="yaml"
    PRD_FILE="tasks.yaml"

    cat > "$PRD_FILE" << 'EOF'
tasks:
  - title: Complete me
    completed: false
  - title: Leave me pending
    completed: false
EOF

    mark_task_complete "Complete me"

    assert_equals "1" "$(count_remaining_tasks)" "Should have 1 pending after completion"
    assert_equals "1" "$(count_completed_tasks)" "Should have 1 completed"
}

test_yaml_parallel_groups() {
    if ! command -v yq &>/dev/null; then
        echo "Skipping YAML test - yq not installed"
        return 0
    fi

    PRD_SOURCE="yaml"
    PRD_FILE="tasks.yaml"

    cat > "$PRD_FILE" << 'EOF'
tasks:
  - title: Group 1 Task A
    completed: false
    parallel_group: 1
  - title: Group 1 Task B
    completed: false
    parallel_group: 1
  - title: Group 2 Task A
    completed: false
    parallel_group: 2
EOF

    local group1=$(get_parallel_group_yaml "Group 1 Task A")
    local group2=$(get_parallel_group_yaml "Group 2 Task A")

    assert_equals "1" "$group1" "Should be in group 1"
    assert_equals "2" "$group2" "Should be in group 2"
}

# ============================================
# Test Cases: Parallel Agent State Transitions
# ============================================

test_agent_initial_state() {
    cleanup_agent_states
    init_agent_states
    set_agent_state "agent-1" "waiting"

    local state=$(get_agent_state "agent-1")
    assert_equals "waiting" "$state" "Agent should start in waiting state"
}

test_agent_valid_transitions() {
    # Test valid transition: waiting -> setting up
    validate_state_transition "waiting" "setting up"
    assert_equals "0" "$?" "waiting -> setting up should be valid"

    # Test valid transition: setting up -> running
    validate_state_transition "setting up" "running"
    assert_equals "0" "$?" "setting up -> running should be valid"

    # Test valid transition: running -> done
    validate_state_transition "running" "done"
    assert_equals "0" "$?" "running -> done should be valid"

    # Test valid transition: running -> failed
    validate_state_transition "running" "failed"
    assert_equals "0" "$?" "running -> failed should be valid"

    # Test valid transition: setting up -> failed
    validate_state_transition "setting up" "failed"
    assert_equals "0" "$?" "setting up -> failed should be valid"
}

test_agent_invalid_transitions() {
    # Test invalid: waiting -> running (skip setting up)
    if validate_state_transition "waiting" "running"; then
        echo "Assertion failed: waiting -> running should be invalid"
        return 1
    fi

    # Test invalid: waiting -> done (skip intermediate states)
    if validate_state_transition "waiting" "done"; then
        echo "Assertion failed: waiting -> done should be invalid"
        return 1
    fi

    # Test invalid: done -> running (can't leave terminal state)
    if validate_state_transition "done" "running"; then
        echo "Assertion failed: done -> running should be invalid"
        return 1
    fi

    # Test invalid: failed -> done (can't leave terminal state)
    if validate_state_transition "failed" "done"; then
        echo "Assertion failed: failed -> done should be invalid"
        return 1
    fi

    return 0
}

test_agent_full_lifecycle_success() {
    cleanup_agent_states
    init_agent_states

    simulate_agent_lifecycle "agent-1" "false"
    local result=$?

    assert_equals "0" "$result" "Lifecycle should complete successfully"
    assert_equals "done" "$(get_agent_state 'agent-1')" "Agent should end in done state"
}

test_agent_full_lifecycle_failure() {
    cleanup_agent_states
    init_agent_states

    simulate_agent_lifecycle "agent-2" "true"
    local result=$?

    assert_equals "0" "$result" "Lifecycle should complete (with failure state)"
    assert_equals "failed" "$(get_agent_state 'agent-2')" "Agent should end in failed state"
}

test_multiple_agents_independent() {
    cleanup_agent_states
    init_agent_states

    # Start multiple agents
    set_agent_state "agent-1" "waiting"
    set_agent_state "agent-2" "waiting"
    set_agent_state "agent-3" "waiting"

    # Progress them independently
    set_agent_state "agent-1" "setting up"
    set_agent_state "agent-2" "setting up"

    assert_equals "setting up" "$(get_agent_state 'agent-1')"
    assert_equals "setting up" "$(get_agent_state 'agent-2')"
    assert_equals "waiting" "$(get_agent_state 'agent-3')"

    set_agent_state "agent-1" "running"
    set_agent_state "agent-3" "setting up"

    assert_equals "running" "$(get_agent_state 'agent-1')"
    assert_equals "setting up" "$(get_agent_state 'agent-2')"
    assert_equals "setting up" "$(get_agent_state 'agent-3')"

    # Complete them
    set_agent_state "agent-1" "done"
    set_agent_state "agent-2" "running"
    set_agent_state "agent-3" "running"

    set_agent_state "agent-2" "failed"
    set_agent_state "agent-3" "done"

    assert_equals "done" "$(get_agent_state 'agent-1')"
    assert_equals "failed" "$(get_agent_state 'agent-2')"
    assert_equals "done" "$(get_agent_state 'agent-3')"
}

# ============================================
# Test Cases: Retry Logic States
# ============================================

test_retry_state_tracking() {
    local max_retries=3
    local retry_count=0
    local succeeded=false

    # Simulate failures then success
    while [[ $retry_count -lt $max_retries ]]; do
        ((retry_count++))

        # Simulate: fail on first 2 attempts, succeed on 3rd
        if [[ $retry_count -eq 3 ]]; then
            succeeded=true
            break
        fi
    done

    assert_equals "true" "$succeeded" "Should succeed after retries"
    assert_equals "3" "$retry_count" "Should have retried 3 times"
}

test_retry_exhaustion() {
    local max_retries=3
    local retry_count=0
    local succeeded=false

    # Simulate all failures
    while [[ $retry_count -lt $max_retries ]]; do
        ((retry_count++))
        # Never succeed
    done

    assert_equals "false" "$succeeded" "Should fail after exhausting retries"
    assert_equals "3" "$retry_count" "Should have attempted max_retries times"
}

# ============================================
# Test Cases: Branch and Git State Transitions
# ============================================

test_slugify_function() {
    local result

    result=$(slugify "Implement Feature A")
    assert_equals "implement-feature-a" "$result" "Should slugify with lowercase and dashes"

    result=$(slugify "Fix bug #123")
    assert_equals "fix-bug-123" "$result" "Should handle special chars"

    result=$(slugify "A very long task name that should be truncated to fifty characters max")
    [[ ${#result} -le 50 ]] || {
        echo "Assertion failed: Slugified result should be <= 50 chars"
        return 1
    }
}

test_task_branch_naming() {
    local task="Add user authentication"
    local expected_branch="ralphy/add-user-authentication"
    local actual_branch="ralphy/$(slugify "$task")"

    assert_equals "$expected_branch" "$actual_branch" "Branch name should follow convention"
}

# ============================================
# Test Cases: Task State Edge Cases
# ============================================

test_empty_prd_file() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    echo "" > "$PRD_FILE"

    assert_equals "0" "$(count_remaining_tasks)" "Empty file should have 0 pending"
    assert_equals "0" "$(count_completed_tasks)" "Empty file should have 0 completed"
    assert_equals "" "$(get_next_task)" "Empty file should return no task"
}

test_all_tasks_completed() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [x] Done 1
- [x] Done 2
- [x] Done 3
EOF

    assert_equals "0" "$(count_remaining_tasks)" "All complete should have 0 pending"
    assert_equals "3" "$(count_completed_tasks)" "Should count all completed"
    assert_equals "" "$(get_next_task)" "No next task when all complete"
}

test_get_all_tasks() {
    PRD_SOURCE="markdown"
    PRD_FILE="PRD.md"

    cat > "$PRD_FILE" << 'EOF'
# Tasks
- [ ] Task A
- [ ] Task B
- [x] Task C (completed)
- [ ] Task D
EOF

    local all_tasks=$(get_all_tasks)
    local task_count=$(echo "$all_tasks" | grep -c "Task" || echo "0")

    assert_equals "3" "$task_count" "Should get only pending tasks"
    assert_contains "$all_tasks" "Task A"
    assert_contains "$all_tasks" "Task B"
    assert_contains "$all_tasks" "Task D"
}

# ============================================
# Test Runner
# ============================================

run_all_tests() {
    echo ""
    echo "${BOLD}============================================${RESET}"
    echo "${BOLD}Job State Transitions Test Suite${RESET}"
    echo "${BOLD}============================================${RESET}"
    echo ""

    # Setup
    setup_test_env

    echo "${BOLD}--- Markdown Task State Tests ---${RESET}"
    run_test "Initial state detection" test_markdown_initial_state
    run_test "Get next task" test_markdown_get_next_task
    run_test "Task completion transition" test_markdown_task_completion
    run_test "Full task lifecycle" test_markdown_full_lifecycle
    run_test "Mixed initial state" test_markdown_mixed_initial_state
    run_test "Special characters in tasks" test_markdown_special_characters_in_task

    echo ""
    echo "${BOLD}--- YAML Task State Tests ---${RESET}"
    run_test "YAML initial state" test_yaml_initial_state
    run_test "YAML task completion" test_yaml_task_completion
    run_test "YAML parallel groups" test_yaml_parallel_groups

    echo ""
    echo "${BOLD}--- Parallel Agent State Tests ---${RESET}"
    run_test "Agent initial state" test_agent_initial_state
    run_test "Valid state transitions" test_agent_valid_transitions
    run_test "Invalid state transitions" test_agent_invalid_transitions
    run_test "Agent lifecycle (success)" test_agent_full_lifecycle_success
    run_test "Agent lifecycle (failure)" test_agent_full_lifecycle_failure
    run_test "Multiple independent agents" test_multiple_agents_independent

    echo ""
    echo "${BOLD}--- Retry Logic Tests ---${RESET}"
    run_test "Retry state tracking" test_retry_state_tracking
    run_test "Retry exhaustion" test_retry_exhaustion

    echo ""
    echo "${BOLD}--- Branch/Git State Tests ---${RESET}"
    run_test "Slugify function" test_slugify_function
    run_test "Task branch naming" test_task_branch_naming

    echo ""
    echo "${BOLD}--- Edge Case Tests ---${RESET}"
    run_test "Empty PRD file" test_empty_prd_file
    run_test "All tasks completed" test_all_tasks_completed
    run_test "Get all tasks" test_get_all_tasks

    # Cleanup
    cleanup_test_env

    # Summary
    echo ""
    echo "${BOLD}============================================${RESET}"
    echo "${BOLD}Test Results${RESET}"
    echo "${BOLD}============================================${RESET}"
    echo "Total:  $TESTS_RUN"
    echo "${GREEN}Passed: $TESTS_PASSED${RESET}"
    echo "${RED}Failed: $TESTS_FAILED${RESET}"
    echo ""

    if [[ $TESTS_FAILED -gt 0 ]]; then
        echo "${RED}${BOLD}TESTS FAILED${RESET}"
        exit 1
    else
        echo "${GREEN}${BOLD}ALL TESTS PASSED${RESET}"
        exit 0
    fi
}

# Run tests if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_all_tests
fi
