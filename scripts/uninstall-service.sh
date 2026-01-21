#!/usr/bin/env bash
#
# Uninstall DVD-to-Plex launchd service
# This script unloads the service and removes the plist file

set -e

SERVICE_LABEL="com.dvdtoplex.service"
PLIST_NAME="${SERVICE_LABEL}.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}"

echo "DVD-to-Plex Service Uninstaller"
echo "================================"

# Check if plist exists
if [ ! -f "$PLIST_PATH" ]; then
    echo "Service plist not found at: $PLIST_PATH"
    echo "The service may not be installed."
    exit 0
fi

# Unload the service if it's currently loaded
echo "Checking if service is loaded..."
if launchctl list | grep -q "$SERVICE_LABEL"; then
    echo "Unloading service..."
    launchctl unload "$PLIST_PATH"
    echo "Service unloaded successfully."
else
    echo "Service is not currently loaded."
fi

# Remove the plist file
echo "Removing plist file..."
rm -f "$PLIST_PATH"
echo "Plist file removed."

echo ""
echo "DVD-to-Plex service has been uninstalled."
echo "Note: The application files and data remain intact."
echo "To reinstall, run: scripts/install-service.sh"
