#!/usr/bin/env bash

# ============================================
# DVDToPlex Service Installer
# Copies launchd plist, updates paths, and loads the service
# ============================================

set -euo pipefail

# Colors (if terminal supports them)
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ $(tput colors 2>/dev/null || echo 0) -ge 8 ]]; then
  RED=$(tput setaf 1)
  GREEN=$(tput setaf 2)
  YELLOW=$(tput setaf 3)
  BOLD=$(tput bold)
  RESET=$(tput sgr0)
else
  RED="" GREEN="" YELLOW="" BOLD="" RESET=""
fi

log_info() { echo "${BOLD}[INFO]${RESET} $*"; }
log_success() { echo "${GREEN}[OK]${RESET} $*"; }
log_warn() { echo "${YELLOW}[WARN]${RESET} $*"; }
log_error() { echo "${RED}[ERROR]${RESET} $*" >&2; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_SOURCE="${PROJECT_DIR}/launchd/com.dvdtoplex.service.plist"
PLIST_NAME="com.dvdtoplex.service.plist"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_DEST="${LAUNCH_AGENTS_DIR}/${PLIST_NAME}"

# Default paths (can be overridden via environment variables)
WORKSPACE_DIR="${WORKSPACE_DIR:-${HOME}/DVDWorkspace}"
VENV_PATH="${VENV_PATH:-${PROJECT_DIR}/.venv}"

show_help() {
  cat << EOF
${BOLD}DVDToPlex Service Installer${RESET}

Usage: $(basename "$0") [OPTIONS]

Options:
  -h, --help          Show this help message
  -u, --unload-first  Unload existing service before installing
  --workspace DIR     Set workspace directory (default: ~/DVDWorkspace)
  --venv PATH         Set Python virtualenv path (default: PROJECT_DIR/.venv)

Environment variables:
  WORKSPACE_DIR       Override default workspace directory
  VENV_PATH           Override default virtualenv path

Examples:
  $(basename "$0")                    # Install with defaults
  $(basename "$0") -u                 # Unload existing, then install
  $(basename "$0") --workspace /data  # Use custom workspace

EOF
}

# Parse arguments
UNLOAD_FIRST=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      show_help
      exit 0
      ;;
    -u|--unload-first)
      UNLOAD_FIRST=true
      shift
      ;;
    --workspace)
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --venv)
      VENV_PATH="$2"
      shift 2
      ;;
    *)
      log_error "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Verify source plist exists
if [[ ! -f "$PLIST_SOURCE" ]]; then
  log_error "Source plist not found: $PLIST_SOURCE"
  log_error "Please ensure launchd/com.dvdtoplex.service.plist exists."
  exit 1
fi

# Create LaunchAgents directory if it doesn't exist
if [[ ! -d "$LAUNCH_AGENTS_DIR" ]]; then
  log_info "Creating ${LAUNCH_AGENTS_DIR}..."
  mkdir -p "$LAUNCH_AGENTS_DIR"
fi

# Unload existing service if requested or if updating
if [[ "$UNLOAD_FIRST" == true ]] || [[ -f "$PLIST_DEST" ]]; then
  if launchctl list | grep -q "com.dvdtoplex.service" 2>/dev/null; then
    log_info "Unloading existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
  fi
fi

# Create workspace directory if it doesn't exist
if [[ ! -d "$WORKSPACE_DIR" ]]; then
  log_info "Creating workspace directory: ${WORKSPACE_DIR}"
  mkdir -p "$WORKSPACE_DIR"
  mkdir -p "${WORKSPACE_DIR}/staging"
  mkdir -p "${WORKSPACE_DIR}/encoding"
  mkdir -p "${WORKSPACE_DIR}/logs"
fi

# Determine Python executable path
if [[ -f "${VENV_PATH}/bin/python" ]]; then
  PYTHON_PATH="${VENV_PATH}/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON_PATH="$(command -v python3)"
else
  log_error "Python not found. Please install Python 3 or create a virtualenv."
  exit 1
fi

# Determine dvdtoplex executable path
if [[ -f "${VENV_PATH}/bin/dvdtoplex" ]]; then
  DVDTOPLEX_PATH="${VENV_PATH}/bin/dvdtoplex"
else
  DVDTOPLEX_PATH="${PYTHON_PATH} -m dvdtoplex"
fi

log_info "Installing service..."
log_info "  Source:    ${PLIST_SOURCE}"
log_info "  Dest:      ${PLIST_DEST}"
log_info "  Workspace: ${WORKSPACE_DIR}"
log_info "  Python:    ${PYTHON_PATH}"

# Copy and update plist with correct paths
# Use sed to replace placeholder paths with actual values
sed \
  -e "s|__WORKSPACE_DIR__|${WORKSPACE_DIR}|g" \
  -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
  -e "s|__PYTHON_PATH__|${PYTHON_PATH}|g" \
  -e "s|__VENV_PATH__|${VENV_PATH}|g" \
  -e "s|__HOME__|${HOME}|g" \
  -e "s|\${HOME}|${HOME}|g" \
  -e "s|\$HOME|${HOME}|g" \
  "$PLIST_SOURCE" > "$PLIST_DEST"

# Set correct permissions
chmod 644 "$PLIST_DEST"

log_success "Plist installed to ${PLIST_DEST}"

# Load the service
log_info "Loading service with launchctl..."
if launchctl load "$PLIST_DEST"; then
  log_success "Service loaded successfully!"
else
  log_error "Failed to load service. Check the plist for errors."
  log_info "You can validate the plist with: plutil -lint ${PLIST_DEST}"
  exit 1
fi

# Verify the service is running
sleep 1
if launchctl list | grep -q "com.dvdtoplex.service"; then
  log_success "Service is now running!"
  echo ""
  echo "${BOLD}Service Status:${RESET}"
  launchctl list | grep "com.dvdtoplex.service" || true
  echo ""
  echo "${BOLD}Useful commands:${RESET}"
  echo "  View logs:      tail -f ${WORKSPACE_DIR}/logs/dvdtoplex.log"
  echo "  Stop service:   launchctl unload ${PLIST_DEST}"
  echo "  Start service:  launchctl load ${PLIST_DEST}"
  echo "  Uninstall:      ${SCRIPT_DIR}/uninstall-service.sh"
else
  log_warn "Service may not have started. Check logs for details."
  log_info "View stdout: cat ${WORKSPACE_DIR}/logs/dvdtoplex.stdout.log"
  log_info "View stderr: cat ${WORKSPACE_DIR}/logs/dvdtoplex.stderr.log"
fi
