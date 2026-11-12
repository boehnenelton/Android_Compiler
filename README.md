# Android Compiler

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm--Noncommercial--1.0.0-DE2626.svg)](LICENSE)
[![Version: 1.0.0](https://img.shields.io/badge/Version-1.0.0-000000.svg)](bejson_project.json)
[![Package: PKG 100](https://img.shields.io/badge/Package-PKG100-000000.svg)](bejson_project.json)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-DE2626.svg)](https://www.python.org/)
[![Platform: Linux / Termux](https://img.shields.io/badge/Platform-Termux%20%7C%20Linux-000000.svg)]()

CLI Android Gradle compiler and build manager featuring persistent target chamber selection and a background Flask web management wrapper.

---

## Architecture Overview

```
Android_Compiler/
├── android_compiler.py       # Main CLI tool with 49-column mobile portrait geometry
├── server_manager.py         # Asynchronous background Flask server manager
├── run.sh                    # Bash launcher for interactive TUI menu
├── app.py                    # Flask REST API and web application server
├── bejson_project.json       # Canonical BEJSON 104a package manifest
├── lib/
│   ├── target_chamber.py     # Persistent target chamber state manager & project scanner
│   └── compiler_engine.py    # Gradle build execution engine & artifact manager
├── templates/
│   └── index.html            # BECSS Tri-Color responsive dashboard
├── static/
│   ├── css/style.css         # Tri-Color stylesheet (#FFFFFF, #000000, #DE2626)
│   └── js/app.js             # Async client controller with live build log streaming
├── config/
│   └── chamber_target.json   # Persistent chamber target lock state
├── data/
│   ├── artifacts.json        # Compiled APK catalog
│   └── build_latest.log      # Active/last execution log
└── tests/
    └── test_android_compiler.py # Conformance test suite
```

---

## Core Capabilities

1. **Persistent Target Chamber Selection**:
   - Discovers Android Gradle projects across environment workspaces dynamically.
   - Locks target project into a chamber (`-t <id|name|path>`), avoiding repetitive path entry.
   - Query loaded target status (`--show-target`), clear target (`--clear`), or switch targets instantaneously.

2. **Full Lifecycle Build Automation**:
   - Debug builds: `assembleDebug` with automatic debug keystore generation and staging.
   - Release builds: `assembleRelease`.
   - Source compilation: `compileDebugSources`.
   - Build cache maintenance: `gradle clean`.
   - Automated artifact extraction, SHA256 checksum calculation, and destination syncing.

3. **On-Device APK Installation**:
   - One-click or single-command installation via `termux-open` and Android Activity Manager VIEW intent.

4. **Web Management Wrapper (Flask)**:
   - Dedicated dashboard with active target metadata card, project selection grid, build triggers, live log streaming, and artifact tray.
   - Asynchronous background execution: Web interface stays responsive while Gradle compiles.
   - Compliant lifecycle manager (`server_manager.py`) with configurable port (`--port 8450`), Termux clipboard URL copy, automatic Chrome launch, and 49-column terminal TUI controls.

---

## CLI Usage

```bash
# Scan and list discovered Android projects
python3 android_compiler.py --list

# Lock target into chamber
python3 android_compiler.py -t BEJSON_Android_Editor

# Query current chamber target
python3 android_compiler.py --show-target

# Build Debug APK on loaded target
python3 android_compiler.py --build

# Build Release APK
python3 android_compiler.py --release

# Install latest compiled APK on device
python3 android_compiler.py --install

# View recent build logs
python3 android_compiler.py --log

# Clear chamber target
python3 android_compiler.py --clear
```

---

## Web Server Lifecycle Management

```bash
# Launch interactive 49-column terminal TUI management menu
./run.sh

# Or manage via CLI commands
python3 server_manager.py start    # Starts background daemon on port 8450
python3 server_manager.py status   # Shows runtime status, PID, and URL
python3 server_manager.py log      # Views last 30 lines of server log
python3 server_manager.py stop     # Stops daemon cleanly
```

---

## Testing

Run the automated test suite:

```bash
python3 -m unittest tests/test_android_compiler.py
```

---

## Author & Attribution

- **Author**: Elton Boehnen
- **Email**: boehnenelton2024@gmail.com
- **Website**: [boehnenelton2024.pages.dev](https://boehnenelton2024.pages.dev)
- **GitHub**: [github.com/boehnenelton](https://github.com/boehnenelton)

## License

This software is licensed under the **PolyForm Noncommercial License 1.0.0** (`PolyForm-Noncommercial-1.0.0`). See [LICENSE](LICENSE) for full details.
