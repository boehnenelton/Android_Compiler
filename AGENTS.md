# Agent Instructions for Android_Compiler

- Project Type: CLI Tool & Flask Web Server
- Runtime: Python 3.10+ on Linux / Android Termux
- Invariants:
  - Dynamic definition resolution from `/storage/emulated/0/.env/user/definitions.json` (no hardcoded environment paths).
  - Mobile Portrait 49-column viewport ceiling for terminal output (`DIVIDER_49`, `SUBDIV_49`).
  - Strict BECSS Tri-Color design (#FFFFFF, #000000, #DE2626) with literal functional labeling.
  - License: PolyForm-Noncommercial-1.0.0.
  - Tests must pass via `python3 -m unittest tests/test_android_compiler.py`.
