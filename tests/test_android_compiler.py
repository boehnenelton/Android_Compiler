#!/data/data/com.termux/files/usr/bin/env python3
"""
# Name:           test_android_compiler.py
# Description:    Unit and conformance test suite for Android Compiler suite
# Version:        100
# Date Created:   2026-11-12
# Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
# License:        PolyForm-Noncommercial-1.0.0
# RELATIONAL_ID:  test-android-compiler-001
"""

from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Setup paths
SUITE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_DIR))

from lib.target_chamber import TargetChamber, ProjectScanner, ProjectInspector
from lib.compiler_engine import CompilerEngine
from app import app


class TestTargetChamber(unittest.TestCase):
    """Test target chamber lock, persistence, and state transitions."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "chamber_target.json"
        self.chamber = TargetChamber(state_file=self.state_file)

        # Create dummy Android project
        self.proj_dir = Path(self.temp_dir) / "MockAndroidApp"
        self.proj_dir.mkdir()
        (self.proj_dir / "build.gradle.kts").write_text('namespace = "com.test.mockapp"')
        (self.proj_dir / "app").mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initial_chamber_is_empty(self):
        active = self.chamber.get_active_target()
        self.assertIsNone(active)

    def test_load_and_persist_target(self):
        rec = self.chamber.load_target(str(self.proj_dir))
        self.assertEqual(rec["name"], "MockAndroidApp")
        self.assertEqual(rec["package_name"], "com.test.mockapp")

        # Verify persisted on disk
        active = self.chamber.get_active_target()
        self.assertIsNotNone(active)
        self.assertEqual(active["path"], str(self.proj_dir))
        self.assertEqual(active["last_status"], "ready")

    def test_record_action_result(self):
        self.chamber.load_target(str(self.proj_dir))
        self.chamber.record_action_result("build", "success", "/path/to/app.apk", "15.2 MB")

        active = self.chamber.get_active_target()
        self.assertEqual(active["last_action"], "build")
        self.assertEqual(active["last_status"], "success")
        self.assertEqual(active["last_apk"], "/path/to/app.apk")
        self.assertEqual(active["last_apk_size"], "15.2 MB")
        self.assertEqual(active["build_count"], 1)

    def test_clear_target(self):
        self.chamber.load_target(str(self.proj_dir))
        self.assertIsNotNone(self.chamber.get_active_target())

        cleared = self.chamber.clear_target()
        self.assertTrue(cleared)
        self.assertIsNone(self.chamber.get_active_target())


class TestProjectScanner(unittest.TestCase):
    """Test project scanning and inspection logic."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Create 2 mock Android projects and 1 non-Android folder
        self.proj1 = Path(self.temp_dir) / "AppOne"
        self.proj1.mkdir()
        (self.proj1 / "build.gradle").write_text('applicationId "com.example.appone"')
        (self.proj1 / "app").mkdir()

        self.proj2 = Path(self.temp_dir) / "AppTwo"
        self.proj2.mkdir()
        (self.proj2 / "settings.gradle.kts").write_text('rootProject.name = "AppTwo"')
        (self.proj2 / "gradle.properties").write_text("org.gradle.jvmargs=-Xmx2048m")

        self.non_proj = Path(self.temp_dir) / "PlainFolder"
        self.non_proj.mkdir()
        (self.non_proj / "readme.txt").write_text("not an android project")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scanner_finds_only_android_projects(self):
        scanner = ProjectScanner(scan_roots=[Path(self.temp_dir)])
        results = scanner.scan()
        names = [r["name"] for r in results]
        self.assertIn("AppOne", names)
        self.assertIn("AppTwo", names)
        self.assertNotIn("PlainFolder", names)

    def test_inspector_extracts_package_name(self):
        inspector = ProjectInspector(self.proj1)
        meta = inspector.inspect()
        self.assertEqual(meta["package_name"], "com.example.appone")


class TestCompilerEngine(unittest.TestCase):
    """Test build engine environment checking and artifact listing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = CompilerEngine(suite_dir=Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_environment_check(self):
        res = self.engine.check_environment()
        self.assertIn("java_home", res)
        self.assertIn("android_home", res)
        self.assertIn("has_gradle", res)

    def test_prepare_project_generates_env(self):
        proj = Path(self.temp_dir) / "TestProj"
        proj.mkdir()
        (proj / ".env.example").write_text("PORT=8080\n")

        notes = self.engine.prepare_project_environment(proj)
        self.assertTrue((proj / ".env").exists())
        self.assertTrue(any("Staged .env" in n for n in notes))


class TestFlaskWrapperApi(unittest.TestCase):
    """Test Flask web app REST endpoints."""

    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_index_route(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Android Compiler", response.data)

    def test_api_status(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("environment", data)
        self.assertIn("build", data)

    def test_api_targets(self):
        response = self.client.get("/api/targets")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["targets"], list)

    def test_api_target_select_and_clear(self):
        # Scan targets first
        t_res = self.client.get("/api/targets")
        targets = t_res.get_json().get("targets", [])
        if targets:
            target_path = targets[0]["path"]
            sel_res = self.client.post("/api/target/select", json={"target": target_path})
            self.assertEqual(sel_res.status_code, 200)
            self.assertEqual(sel_res.get_json()["status"], "ok")

        # Clear target
        clear_res = self.client.post("/api/target/clear")
        self.assertEqual(clear_res.status_code, 200)
        self.assertEqual(clear_res.get_json()["status"], "ok")

    def test_api_artifacts(self):
        response = self.client.get("/api/artifacts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["artifacts"], list)


if __name__ == "__main__":
    unittest.main()
