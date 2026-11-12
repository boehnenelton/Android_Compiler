#!/data/data/com.termux/files/usr/bin/env python3
"""
# Name:           app.py
# Description:    Flask web interface wrapper for Android compiler & target chamber
# Version:        100
# Date Created:   2026-11-12
# Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
# License:        PolyForm-Noncommercial-1.0.0
# RELATIONAL_ID:  web-android-compiler-001
"""

from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory

SCRIPT_PATH = Path(__file__).resolve()
SUITE_DIR = SCRIPT_PATH.parent
sys.path.insert(0, str(SUITE_DIR))

from lib.target_chamber import TargetChamber, ProjectScanner
from lib.compiler_engine import CompilerEngine

# Configure standard logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("android_compiler.web")

app = Flask(
    __name__,
    template_folder=str(SUITE_DIR / "templates"),
    static_folder=str(SUITE_DIR / "static"),
)

chamber = TargetChamber()
engine = CompilerEngine(suite_dir=SUITE_DIR)


def on_build_completed(action: str, exit_code: int, apk_info: dict | None) -> None:
    """Callback when async build finishes."""
    status_str = "success" if exit_code == 0 else "failed"
    apk_path = apk_info.get("path") if apk_info else None
    apk_size = apk_info.get("size_human") if apk_info else None
    chamber.record_action_result(action, status_str, apk_path, apk_size)
    logger.info("Build completed: action=%s exit=%d apk=%s", action, exit_code, apk_path)


@app.route("/")
def index():
    """Render main compiler dashboard."""
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    """Get active chamber target, engine state, and environment diagnostics."""
    active = chamber.get_active_target()
    b_status = engine.get_status()
    env_info = engine.check_environment()
    return jsonify({
        "status": "ok",
        "active_target": active,
        "build": b_status,
        "environment": env_info,
    })


@app.route("/api/targets", methods=["GET"])
def api_targets():
    """Scan and list discovered Android projects."""
    scanner = ProjectScanner()
    projects = scanner.scan()
    active = chamber.get_active_target()
    active_path = active.get("path") if active else None

    for p in projects:
        p["is_active"] = (p["path"] == active_path)

    return jsonify({
        "status": "ok",
        "targets": projects,
        "count": len(projects),
    })


@app.route("/api/target/select", methods=["POST"])
def api_target_select():
    """Load target into chamber by path or name."""
    data = request.get_json(silent=True) or {}
    target_val = data.get("target") or data.get("path")
    if not target_val:
        return jsonify({"status": "error", "message": "Target parameter required"}), 400

    try:
        record = chamber.load_target(str(target_val))
        return jsonify({
            "status": "ok",
            "message": f"Target loaded: {record['name']}",
            "target": record,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/target/clear", methods=["POST"])
def api_target_clear():
    """Clear currently loaded target."""
    chamber.clear_target()
    return jsonify({"status": "ok", "message": "Target chamber cleared"})


@app.route("/api/build", methods=["POST"])
def api_build():
    """Trigger build action asynchronously on loaded target."""
    active = chamber.get_active_target()
    if not active:
        return jsonify({"status": "error", "message": "No target loaded in chamber"}), 400

    data = request.get_json(silent=True) or {}
    action = data.get("action", "debug").lower()
    valid_actions = ["debug", "build", "release", "compile", "clean"]
    if action not in valid_actions:
        return jsonify({"status": "error", "message": f"Invalid action. Choose from: {valid_actions}"}), 400

    if engine.is_building:
        return jsonify({"status": "busy", "message": "Build already in progress"}), 409

    target_path = active["path"]
    started = engine.run_action_async(target_path, action, on_complete=on_build_completed)
    if started:
        return jsonify({
            "status": "ok",
            "message": f"Started {action} build on {active['name']}",
            "action": action,
            "target": active["name"],
        })
    return jsonify({"status": "error", "message": "Failed to launch build process"}), 500


@app.route("/api/build/status", methods=["GET"])
def api_build_status():
    """Query build execution status."""
    return jsonify({
        "status": "ok",
        "build": engine.get_status(),
    })


@app.route("/api/build/log", methods=["GET"])
def api_build_log():
    """Return latest build log lines."""
    lines_count = request.args.get("lines", default=100, type=int)
    if not engine.log_file.exists():
        return jsonify({"status": "ok", "log": "No build log available yet.\n", "total_lines": 0})
    try:
        content = engine.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        slice_lines = content[-lines_count:]
        return jsonify({
            "status": "ok",
            "log": "\n".join(slice_lines),
            "total_lines": len(content),
            "is_building": engine.is_building,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/artifacts", methods=["GET"])
def api_artifacts():
    """List compiled APK artifacts."""
    artifacts = engine.list_artifacts()
    return jsonify({
        "status": "ok",
        "artifacts": artifacts,
        "count": len(artifacts),
    })


@app.route("/api/install", methods=["POST"])
def api_install():
    """Trigger device installation for APK."""
    data = request.get_json(silent=True) or {}
    apk_path = data.get("apk_path")
    ok, message = engine.install_apk(apk_path)
    if ok:
        return jsonify({"status": "ok", "message": message})
    return jsonify({"status": "error", "message": message}), 500


@app.route("/download/<path:filename>")
def download_artifact(filename: str):
    """Serve APK artifact for download."""
    return send_from_directory(str(engine.artifacts_dir), filename, as_attachment=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.py", description="Android Compiler Flask Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8450, help="Port to bind")
    args = parser.parse_args()

    logger.info("Starting Android Compiler Flask Server on http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
