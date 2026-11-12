#!/data/data/com.termux/files/usr/bin/env python3
"""
# Name:           compiler_engine.py
# Description:    Android Gradle build execution engine and artifact manager
# Version:        100
# Date Created:   2026-11-12
# Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
# License:        PolyForm-Noncommercial-1.0.0
# RELATIONAL_ID:  lib-compiler-engine-001
"""

from __future__ import annotations
import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("android_compiler.engine")

DEFINITIONS_FILE = Path("/storage/emulated/0/.env/user/definitions.json")


def resolve_def(key: str, fallback: str) -> str:
    """Resolve environment path dynamically from definitions.json."""
    if DEFINITIONS_FILE.exists():
        try:
            with open(DEFINITIONS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for row in data.get("Values", []):
                if len(row) >= 2 and row[0] == key:
                    return str(row[1])
        except Exception:
            pass
    return fallback


class CompilerEngine:
    """Manages Android Gradle builds, logging, and artifact generation."""

    def __init__(self, suite_dir: Optional[Path] = None) -> None:
        if suite_dir is None:
            self.suite_dir = Path(__file__).resolve().parent.parent
        else:
            self.suite_dir = suite_dir
        self.data_dir = self.suite_dir / "data"
        self.artifacts_dir = self.data_dir / "artifacts"
        self.log_file = self.data_dir / "build_latest.log"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.java_home = os.environ.get(
            "JAVA_HOME",
            "/data/data/com.termux/files/usr/lib/jvm/java-21-openjdk",
        )
        self.android_home = os.environ.get(
            "ANDROID_HOME",
            resolve_def("ANDROID_SDK", "/data/data/com.termux/files/home/android-sdk"),
        )
        self.output_dest = resolve_def("ADMIN_ANDROID", "/storage/emulated/0/Admin/Dev/Android")

        # Current build execution state
        self._lock = threading.Lock()
        self.is_building = False
        self.current_action: Optional[str] = None
        self.current_project: Optional[str] = None
        self.build_start_time: Optional[float] = None
        self.last_exit_code: Optional[int] = None

    def check_environment(self) -> Dict[str, Any]:
        """Verify presence of Java, Android SDK, and Gradle tools."""
        java_bin = Path(self.java_home) / "bin" / "java"
        javac_bin = Path(self.java_home) / "bin" / "javac"
        sdk_dir = Path(self.android_home)
        has_gradle = shutil.which("gradle") is not None

        errors = []
        if not java_bin.exists():
            errors.append(f"Java runtime not found at {java_bin}")
        if not sdk_dir.exists():
            errors.append(f"Android SDK directory not found at {sdk_dir}")
        if not has_gradle:
            errors.append("System 'gradle' command not found in PATH")

        return {
            "valid": len(errors) == 0,
            "java_home": self.java_home,
            "android_home": self.android_home,
            "has_gradle": has_gradle,
            "errors": errors,
        }

    def prepare_project_environment(self, project_dir: Path) -> List[str]:
        """Ensure necessary signing keystore and env files exist."""
        notes = []
        # Ensure .env exists if .env.example is present
        env_file = project_dir / ".env"
        env_example = project_dir / ".env.example"
        if not env_file.exists() and env_example.exists():
            shutil.copy(env_example, env_file)
            notes.append("Staged .env from .env.example")

        # Ensure debug.keystore exists
        keystore_file = project_dir / "debug.keystore"
        if not keystore_file.exists():
            keytool_cmd = [
                f"{self.java_home}/bin/keytool",
                "-genkey", "-v",
                "-keystore", str(keystore_file),
                "-storepass", "android",
                "-alias", "androiddebugkey",
                "-keypass", "android",
                "-keyalg", "RSA",
                "-keysize", "2048",
                "-validity", "10000",
                "-dname", "CN=Android Debug,O=Android,C=US",
            ]
            try:
                subprocess.run(keytool_cmd, check=True, capture_output=True, timeout=20)
                notes.append("Generated debug.keystore for APK signing")
            except Exception as exc:
                notes.append(f"Could not generate debug.keystore: {exc}")

        return notes

    def get_build_env(self) -> Dict[str, str]:
        """Construct sanitized environment variables dictionary."""
        env = os.environ.copy()
        env["JAVA_HOME"] = self.java_home
        env["ANDROID_HOME"] = self.android_home
        env["ANDROID_SDK_ROOT"] = self.android_home

        path_entries = [
            f"{self.java_home}/bin",
            f"{self.android_home}/cmdline-tools/latest/bin",
            f"{self.android_home}/platform-tools",
            "/data/data/com.termux/files/usr/bin",
            env.get("PATH", ""),
        ]
        env["PATH"] = ":".join(p for p in path_entries if p)
        return env

    def run_action_async(
        self,
        project_dir_str: str,
        action: str,
        on_complete: Optional[Callable[[str, int, Optional[Dict[str, Any]]], None]] = None,
    ) -> bool:
        """Start build task in a background daemon thread."""
        with self._lock:
            if self.is_building:
                return False
            self.is_building = True
            self.current_action = action
            self.current_project = Path(project_dir_str).name
            self.build_start_time = time.time()
            self.last_exit_code = None

        thread = threading.Thread(
            target=self._worker_run,
            args=(project_dir_str, action, on_complete),
            daemon=True,
        )
        thread.start()
        return True

    def _worker_run(
        self,
        project_dir_str: str,
        action: str,
        on_complete: Optional[Callable[[str, int, Optional[Dict[str, Any]]], None]] = None,
    ) -> None:
        """Worker thread entrypoint."""
        project_dir = Path(project_dir_str).resolve()
        code, apk_info = self.execute_action(project_dir, action)

        with self._lock:
            self.is_building = False
            self.last_exit_code = code

        if on_complete:
            try:
                on_complete(action, code, apk_info)
            except Exception as exc:
                logger.error("Error in on_complete callback: %s", exc)

    def execute_action(
        self,
        project_dir: Path,
        action: str,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Execute Gradle command synchronously, logging stdout/stderr."""
        self.prepare_project_environment(project_dir)
        env = self.get_build_env()

        # Map action to Gradle tasks
        action_map = {
            "debug": "assembleDebug",
            "build": "assembleDebug",
            "release": "assembleRelease",
            "compile": "compileDebugSources",
            "clean": "clean",
        }
        gradle_task = action_map.get(action.lower(), "assembleDebug")

        # Determine gradle executable (wrapper or system)
        gradle_cmd = "gradle"
        wrapper = project_dir / "gradlew"
        if wrapper.is_file() and os.access(wrapper, os.X_OK):
            gradle_cmd = str(wrapper)

        cmd = [gradle_cmd, "-p", str(project_dir), gradle_task]

        # Reset log file
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(self.log_file, "w", encoding="utf-8") as lf:
            lf.write(f"=== BUILD STARTED: {now_str} ===\n")
            lf.write(f"Project: {project_dir}\n")
            lf.write(f"Action:  {action} -> Task: {gradle_task}\n")
            lf.write(f"Command: {' '.join(cmd)}\n")
            lf.write("=" * 49 + "\n\n")

        apk_info: Optional[Dict[str, Any]] = None
        exit_code = 1

        try:
            with open(self.log_file, "a", encoding="utf-8") as lf:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(project_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                if proc.stdout:
                    for line in proc.stdout:
                        lf.write(line)
                        lf.flush()
                proc.wait()
                exit_code = proc.returncode

            with open(self.log_file, "a", encoding="utf-8") as lf:
                end_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                lf.write("\n" + "=" * 49 + "\n")
                lf.write(f"=== BUILD FINISHED: {end_str} (Exit: {exit_code}) ===\n")

            if exit_code == 0 and action in ("build", "debug", "release"):
                apk_info = self._collect_artifact(project_dir, action)

        except Exception as exc:
            with open(self.log_file, "a", encoding="utf-8") as lf:
                lf.write(f"\n[ERROR] Process execution failed: {exc}\n")
            exit_code = 2

        return exit_code, apk_info

    def _collect_artifact(self, project_dir: Path, action: str) -> Optional[Dict[str, Any]]:
        """Locate generated APK, copy to output destinations, record metadata."""
        variant = "release" if action == "release" else "debug"
        search_dirs = [
            project_dir / "app" / "build" / "outputs" / "apk" / variant,
            project_dir / "build" / "outputs" / "apk" / variant,
            project_dir / "app" / "build" / "outputs" / "apk",
        ]

        found_apk: Optional[Path] = None
        for sdir in search_dirs:
            if sdir.is_dir():
                for apk in sdir.glob("*.apk"):
                    found_apk = apk
                    break
            if found_apk:
                break

        if not found_apk:
            return None

        # Standard naming: <ProjectName>_<variant>.apk
        proj_name = project_dir.name
        final_filename = f"{proj_name}_{variant}.apk"

        # Copy to suite artifacts
        dest_artifact = self.artifacts_dir / final_filename
        shutil.copy2(found_apk, dest_artifact)

        # Copy to ADMIN_ANDROID root if available
        output_dir = Path(self.output_dest)
        if output_dir.exists() and output_dir.is_dir():
            dest_admin = output_dir / final_filename
            try:
                shutil.copy2(found_apk, dest_admin)
            except Exception as exc:
                logger.warning("Could not copy to ADMIN_ANDROID: %s", exc)

        # Extract size and hash
        size_bytes = dest_artifact.stat().st_size
        size_human = self._human_size(size_bytes)
        sha256 = self._compute_sha256(dest_artifact)

        info = {
            "name": final_filename,
            "path": str(dest_artifact),
            "admin_path": str(output_dir / final_filename) if output_dir.exists() else str(dest_artifact),
            "size_bytes": size_bytes,
            "size_human": size_human,
            "sha256": sha256,
            "variant": variant,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Append to artifacts manifest
        self._record_artifact_manifest(info)
        return info

    def _human_size(self, size_bytes: int) -> str:
        """Format byte size into human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _compute_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as fh:
            while chunk := fh.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _record_artifact_manifest(self, info: Dict[str, Any]) -> None:
        """Save artifact entry into data/artifacts.json."""
        manifest_file = self.data_dir / "artifacts.json"
        records = []
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as fh:
                    records = json.load(fh)
            except Exception:
                records = []

        # Filter out older record with same name
        records = [r for r in records if r.get("name") != info["name"]]
        records.insert(0, info)
        try:
            with open(manifest_file, "w", encoding="utf-8") as fh:
                json.dump(records[:20], fh, indent=2)
        except Exception as exc:
            logger.warning("Could not update artifacts.json: %s", exc)

    def list_artifacts(self) -> List[Dict[str, Any]]:
        """Return list of available compiled APKs."""
        manifest_file = self.data_dir / "artifacts.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as fh:
                    items = json.load(fh)
                # Verify files exist on disk
                return [i for i in items if Path(i["path"]).exists()]
            except Exception:
                pass

        # Fallback: scan artifacts folder directly
        items = []
        for apk in self.artifacts_dir.glob("*.apk"):
            size_bytes = apk.stat().st_size
            items.append({
                "name": apk.name,
                "path": str(apk),
                "admin_path": str(Path(self.output_dest) / apk.name),
                "size_bytes": size_bytes,
                "size_human": self._human_size(size_bytes),
                "sha256": "",
                "variant": "debug" if "debug" in apk.name else "release",
                "created_at": datetime.fromtimestamp(apk.stat().st_mtime, timezone.utc).isoformat(),
            })
        return sorted(items, key=lambda x: x["created_at"], reverse=True)

    def install_apk(self, apk_path_str: Optional[str] = None) -> Tuple[bool, str]:
        """Dispatch APK installation via termux-open or Android intent."""
        target_path: Optional[Path] = None
        if apk_path_str:
            p = Path(apk_path_str)
            if p.exists():
                target_path = p
        if not target_path:
            artifacts = self.list_artifacts()
            if artifacts:
                target_path = Path(artifacts[0]["path"])

        if not target_path or not target_path.exists():
            return False, "No compiled APK found to install."

        # Attempt Termux open first
        try:
            res = subprocess.run(
                ["termux-open", str(target_path)],
                check=False,
                capture_output=True,
                timeout=5,
            )
            if res.returncode == 0:
                return True, f"Installation launched via termux-open for {target_path.name}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: Android Activity Manager VIEW intent
        try:
            cmd = [
                "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", f"file://{target_path}",
                "-t", "application/vnd.android.package-archive",
            ]
            res = subprocess.run(cmd, check=False, capture_output=True, timeout=5)
            if res.returncode == 0:
                return True, f"Installation launched via Android intent for {target_path.name}"
            return False, f"Install failed with code {res.returncode}: {res.stderr.decode()}"
        except Exception as exc:
            return False, f"Could not launch installer: {exc}"

    def get_status(self) -> Dict[str, Any]:
        """Return runtime build execution status."""
        elapsed = 0.0
        if self.is_building and self.build_start_time:
            elapsed = round(time.time() - self.build_start_time, 1)

        return {
            "is_building": self.is_building,
            "current_action": self.current_action,
            "current_project": self.current_project,
            "elapsed_seconds": elapsed,
            "last_exit_code": self.last_exit_code,
        }
