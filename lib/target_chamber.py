#!/data/data/com.termux/files/usr/bin/env python3
"""
# Name:           target_chamber.py
# Description:    Target chamber state manager and Android project scanner
# Version:        100
# Date Created:   2026-11-12
# Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
# License:        PolyForm-Noncommercial-1.0.0
# RELATIONAL_ID:  lib-target-chamber-001
"""

from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("android_compiler.chamber")

DEFINITIONS_FILE = Path("/storage/emulated/0/.env/user/definitions.json")


def resolve_definition(key: str, fallback: str) -> str:
    """Resolve environment path dynamically from definitions.json."""
    if DEFINITIONS_FILE.exists():
        try:
            with open(DEFINITIONS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for row in data.get("Values", []):
                if len(row) >= 2 and row[0] == key:
                    return str(row[1])
        except Exception as exc:
            logger.warning("Could not read definitions file for %s: %s", key, exc)
    return fallback


def get_default_scan_roots() -> List[Path]:
    """Retrieve default search directories for Android projects."""
    roots: List[Path] = []
    admin_android = resolve_definition("ADMIN_ANDROID", "/storage/emulated/0/Admin/Dev/Android")
    p = Path(admin_android)
    if p.exists() and p.is_dir():
        roots.append(p)
    return roots


class TargetChamber:
    """Manages the persistent loaded chamber target state."""

    def __init__(self, state_file: Optional[Path] = None) -> None:
        if state_file is None:
            suite_dir = Path(__file__).resolve().parent.parent
            self.state_file = suite_dir / "config" / "chamber_target.json"
        else:
            self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        """Read active target state atomically."""
        if not self.state_file.exists():
            return {
                "active_target": None,
                "history": [],
                "updated_at": None,
            }
        try:
            with open(self.state_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.error("Failed to read chamber target state: %s", exc)
            return {"active_target": None, "history": [], "updated_at": None}

    def save_state(self, state: Dict[str, Any]) -> bool:
        """Save chamber state atomically with tempfile replace."""
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
            temp_file.replace(self.state_file)
            return True
        except Exception as exc:
            logger.error("Failed to write chamber target state: %s", exc)
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            return False

    def get_active_target(self) -> Optional[Dict[str, Any]]:
        """Return currently loaded target details or None."""
        state = self.load_state()
        return state.get("active_target")

    def load_target(self, project_path: str, scan_roots: Optional[List[Path]] = None) -> Dict[str, Any]:
        """Load an Android project into the chamber."""
        resolved = Path(project_path).resolve()
        if not resolved.exists() or not resolved.is_dir():
            # Check by name in scanned projects
            projects = ProjectScanner(scan_roots).scan()
            matched = next((p for p in projects if p["name"].lower() == project_path.lower() or p["slug"] == project_path.lower()), None)
            if matched:
                resolved = Path(matched["path"])
            else:
                raise ValueError(f"Project path or target does not exist: {project_path}")

        # Validate that it is an Android project
        inspector = ProjectInspector(resolved)
        meta = inspector.inspect()

        state = self.load_state()
        now_iso = datetime.now(timezone.utc).isoformat()

        target_record = {
            "name": meta["name"],
            "slug": meta["slug"],
            "path": str(resolved),
            "package_name": meta.get("package_name", "unknown"),
            "has_wrapper": meta["has_wrapper"],
            "loaded_at": now_iso,
            "last_action": None,
            "last_status": "ready",
            "last_apk": None,
            "last_apk_size": None,
            "build_count": (state.get("active_target") or {}).get("build_count", 0),
        }

        state["active_target"] = target_record
        state["updated_at"] = now_iso
        self.save_state(state)
        return target_record

    def clear_target(self) -> bool:
        """Clear the loaded chamber target."""
        state = self.load_state()
        if state.get("active_target"):
            prev = state["active_target"]
            state["history"] = state.get("history", [])[-19:] + [prev]
        state["active_target"] = None
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self.save_state(state)

    def record_action_result(
        self,
        action: str,
        status: str,
        apk_path: Optional[str] = None,
        apk_size: Optional[str] = None,
    ) -> None:
        """Update active target with outcome of execution action."""
        state = self.load_state()
        active = state.get("active_target")
        if not active:
            return
        active["last_action"] = action
        active["last_status"] = status
        if apk_path:
            active["last_apk"] = apk_path
            active["last_apk_size"] = apk_size
        if status == "success" and action in ("build", "release", "debug"):
            active["build_count"] = active.get("build_count", 0) + 1
        active["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["active_target"] = active
        self.save_state(state)


class ProjectInspector:
    """Extracts metadata from an Android project directory."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def inspect(self) -> Dict[str, Any]:
        """Examine project structure and manifest/gradle configs."""
        name = self.project_path.name
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name).lower()
        has_wrapper = (self.project_path / "gradlew").is_file()
        has_gradle = (
            (self.project_path / "build.gradle").is_file()
            or (self.project_path / "build.gradle.kts").is_file()
            or (self.project_path / "settings.gradle").is_file()
            or (self.project_path / "settings.gradle.kts").is_file()
        )

        package_name = self._detect_package_name()

        return {
            "name": name,
            "slug": slug,
            "path": str(self.project_path),
            "has_wrapper": has_wrapper,
            "has_gradle": has_gradle,
            "package_name": package_name,
        }

    def _detect_package_name(self) -> str:
        """Find namespace or applicationId in build files or manifest."""
        # Check app/build.gradle.kts or app/build.gradle
        for rel in ["app/build.gradle.kts", "app/build.gradle", "build.gradle.kts", "build.gradle"]:
            f = self.project_path / rel
            if f.is_file():
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r'(?:namespace|applicationId)\s*[=\s]\s*["\']([^"\']+)["\']', content)
                    if m:
                        return m.group(1)
                except Exception:
                    pass

        # Check AndroidManifest.xml
        for rel in ["app/src/main/AndroidManifest.xml", "src/main/AndroidManifest.xml"]:
            f = self.project_path / rel
            if f.is_file():
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r'package\s*=\s*["\']([^"\']+)["\']', content)
                    if m:
                        return m.group(1)
                except Exception:
                    pass

        return "com.example.android"


class ProjectScanner:
    """Discovers Android projects across specified root paths."""

    def __init__(self, scan_roots: Optional[List[Path]] = None) -> None:
        if scan_roots is None:
            self.scan_roots = get_default_scan_roots()
        else:
            self.scan_roots = scan_roots

    def scan(self) -> List[Dict[str, Any]]:
        """Find all Android directories with Gradle indicators."""
        results: List[Dict[str, Any]] = []
        seen_paths = set()

        for root in self.scan_roots:
            if not root.exists() or not root.is_dir():
                continue
            # Check root itself
            if self._is_android_project(root):
                if str(root) not in seen_paths:
                    meta = ProjectInspector(root).inspect()
                    results.append(meta)
                    seen_paths.add(str(root))
                continue

            # Check direct children
            try:
                for entry in os.scandir(root):
                    if entry.is_dir() and not entry.name.startswith("."):
                        child_path = Path(entry.path)
                        if self._is_android_project(child_path):
                            if str(child_path) not in seen_paths:
                                meta = ProjectInspector(child_path).inspect()
                                results.append(meta)
                                seen_paths.add(str(child_path))
            except (PermissionError, FileNotFoundError) as exc:
                logger.warning("Scan error in %s: %s", root, exc)

        return sorted(results, key=lambda x: x["name"])

    def _is_android_project(self, path: Path) -> bool:
        """Determine if a directory is an Android build directory."""
        # Avoid treating Android_Compiler itself as an android project to build
        if path.name.lower() in ("android_compiler", "android_compiler_tmp"):
            return False
        indicators = [
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        ]
        has_gradle = any((path / ind).exists() for ind in indicators)
        has_app_or_src = (path / "app").is_dir() or (path / "src").is_dir()
        return has_gradle and (has_app_or_src or (path / "gradle.properties").exists())
