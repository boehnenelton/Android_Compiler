#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# run.sh | Android Compiler Flask Server Launcher
# Version: 1.0.0 | Date: 2026-11-12 | Author: Elton Boehnen
# License: PolyForm-Noncommercial-1.0.0
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" "$SCRIPT_DIR/server_manager.py" "$@"
