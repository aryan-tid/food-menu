#!/bin/bash
# ==============================================================================
# Spice Garden Restaurant System - GCP Deployment Wrapper
# Repository: https://github.com/aryan-tid/food-menu.git
# ==============================================================================
# Usage:
#   First-Time Setup: sudo bash gcp/deploy_first_time.sh
#   Update Existing:  sudo bash gcp/update_app.sh
#   Wrapper usage:
#     sudo bash gcp/deploy.sh             (Runs first-time deploy)
#     sudo bash gcp/deploy.sh --update    (Runs app update from GitHub)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$1" == "--update" ] || [ "$1" == "-u" ] || [ "$1" == "update" ]; then
    exec bash "$SCRIPT_DIR/update_app.sh"
fi

exec bash "$SCRIPT_DIR/deploy_first_time.sh" "$@"
