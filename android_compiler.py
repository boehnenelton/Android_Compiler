#!/data/data/com.termux/files/usr/bin/env python3
"""
# Name:           android_compiler.py
# Description:    CLI Android compiler with target chamber selection & build dispatch
# Version:        100
# Date Created:   2026-11-12
# Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
# License:        PolyForm-Noncommercial-1.0.0
# RELATIONAL_ID:  cli-android-compiler-001
"""

from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

# Add suite directory to sys.path
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
logger = logging.getLogger("android_compiler.cli")

# 49-Column mobile portrait terminal geometry
DIVIDER_49 = "=" * 49
SUBDIV_49 = "-" * 49

# ANSI color codes
RED = "\033[38;2;222;38;38m"
WHITE = "\033[1;37m"
DIM = "\033[0;37m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RESET = "\033[0m"


def print_banner() -> None:
    print(f"{RED}{DIVIDER_49}{RESET}")
    print(f"{WHITE} ANDROID COMPILER CLI{RESET}")
    print(f"{DIM} Target Chamber & Build Dispatch v1.0.0{RESET}")
    print(f"{RED}{DIVIDER_49}{RESET}")


def cmd_list(chamber: TargetChamber) -> None:
    """Scan and list discovered Android projects."""
    print(f"{DIM}{SUBDIV_49}{RESET}")
    print(f"{WHITE} AVAILABLE ANDROID TARGETS{RESET}")
    print(f"{DIM}{SUBDIV_49}{RESET}")

    scanner = ProjectScanner()
    projects = scanner.scan()
    active = chamber.get_active_target()
    active_path = active.get("path") if active else None

    if not projects:
        print(f"{YELLOW}No Android Gradle projects discovered.{RESET}")
        return

    for idx, p in enumerate(projects, start=1):
        is_active = (p["path"] == active_path)
        tag = f"{RED}[ACTIVE]{RESET} " if is_active else f"[{idx:2d}] "
        print(f"{tag}{WHITE}{p['name']}{RESET}")
        print(f"     Path: {DIM}{p['path']}{RESET}")
        print(f"     Pkg:  {DIM}{p.get('package_name', 'unknown')}{RESET}")

    print(f"{DIM}{SUBDIV_49}{RESET}")
    print(f"Use '{CYAN}android_compiler.py -t <number|name>{RESET}' to select.")


def cmd_show_target(chamber: TargetChamber) -> None:
    """Display the currently loaded chamber target."""
    active = chamber.get_active_target()
    print(f"{DIM}{SUBDIV_49}{RESET}")
    print(f"{WHITE} ACTIVE TARGET STATUS{RESET}")
    print(f"{DIM}{SUBDIV_49}{RESET}")

    if not active:
        print(f"{YELLOW}No target loaded in chamber.{RESET}")
        print(f"Run '{CYAN}android_compiler.py --list{RESET}' to inspect available projects.")
        return

    print(f" {RED}Target Name:{RESET}  {WHITE}{active['name']}{RESET}")
    print(f" {RED}Path:{RESET}         {DIM}{active['path']}{RESET}")
    print(f" {RED}Package:{RESET}      {DIM}{active.get('package_name', 'unknown')}{RESET}")
    print(f" {RED}Loaded At:{RESET}    {DIM}{active.get('loaded_at', '—')}{RESET}")
    print(f" {RED}Last Action:{RESET}  {WHITE}{active.get('last_action') or 'none'}{RESET}")
    print(f" {RED}Last Status:{RESET}  {GREEN if active.get('last_status') == 'success' else YELLOW}{active.get('last_status') or 'ready'}{RESET}")
    if active.get("last_apk"):
        print(f" {RED}Last APK:{RESET}     {CYAN}{active['last_apk']}{RESET}")
        print(f" {RED}APK Size:{RESET}     {DIM}{active.get('last_apk_size', '—')}{RESET}")
    print(f" {RED}Build Count:{RESET}  {DIM}{active.get('build_count', 0)}{RESET}")
    print(f"{DIM}{SUBDIV_49}{RESET}")


def cmd_load_target(chamber: TargetChamber, target_arg: str) -> None:
    """Load target by index, name, or path."""
    scanner = ProjectScanner()
    projects = scanner.scan()

    resolved_path: str = target_arg

    # Check if target_arg is numeric index
    if target_arg.isdigit():
        idx = int(target_arg)
        if 1 <= idx <= len(projects):
            resolved_path = projects[idx - 1]["path"]
        else:
            print(f"{RED}[✗] Invalid index: {idx}. Total projects: {len(projects)}{RESET}")
            return

    try:
        record = chamber.load_target(resolved_path)
        print(f"{GREEN}[✓] Target locked into chamber:{RESET} {WHITE}{record['name']}{RESET}")
        print(f"    Path: {DIM}{record['path']}{RESET}")
    except ValueError as exc:
        print(f"{RED}[✗] Target lock failed: {exc}{RESET}")


def cmd_clear_target(chamber: TargetChamber) -> None:
    """Clear currently loaded chamber target."""
    active = chamber.get_active_target()
    if not active:
        print(f"{DIM}[*] Chamber is already empty.{RESET}")
        return
    chamber.clear_target()
    print(f"{GREEN}[✓] Target unlocked: {active['name']} removed from chamber.{RESET}")


def cmd_execute_action(chamber: TargetChamber, engine: CompilerEngine, action: str) -> int:
    """Execute build action on the loaded target."""
    active = chamber.get_active_target()
    if not active:
        print(f"{RED}[✗] No target loaded in chamber!{RESET}")
        print(f"    Select a target first: '{CYAN}android_compiler.py -t <name>{RESET}'")
        return 1

    project_dir = Path(active["path"])
    if not project_dir.exists():
        print(f"{RED}[✗] Target directory does not exist: {project_dir}{RESET}")
        return 1

    print(f"{DIM}{SUBDIV_49}{RESET}")
    print(f"{WHITE} EXECUTION: {action.upper()}{RESET}")
    print(f" Target: {WHITE}{active['name']}{RESET}")
    print(f"{DIM}{SUBDIV_49}{RESET}")

    code, apk_info = engine.execute_action(project_dir, action)

    status_str = "success" if code == 0 else "failed"
    apk_path = apk_info.get("path") if apk_info else None
    apk_size = apk_info.get("size_human") if apk_info else None

    chamber.record_action_result(action, status_str, apk_path, apk_size)

    if code == 0:
        print(f"{GREEN}[✓] ACTION COMPLETED SUCCESSFULLY ({action}){RESET}")
        if apk_info:
            print(f"    APK:  {CYAN}{apk_info['path']}{RESET}")
            print(f"    Size: {YELLOW}{apk_info['size_human']}{RESET}")
            if apk_info.get("admin_path") != apk_info["path"]:
                print(f"    Dest: {DIM}{apk_info['admin_path']}{RESET}")
    else:
        print(f"{RED}[✗] ACTION FAILED with exit code {code}{RESET}")
        print(f"    Inspect log: '{CYAN}android_compiler.py --log{RESET}'")

    return code


def cmd_install(engine: CompilerEngine) -> int:
    """Launch APK installer."""
    ok, msg = engine.install_apk()
    if ok:
        print(f"{GREEN}[✓] {msg}{RESET}")
        return 0
    else:
        print(f"{RED}[✗] {msg}{RESET}")
        return 1


def cmd_view_log(engine: CompilerEngine, lines: int = 40) -> None:
    """Print the tail of build log."""
    if not engine.log_file.exists():
        print(f"{YELLOW}No build log exists yet.{RESET}")
        return
    content = engine.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"{DIM}{SUBDIV_49}{RESET}")
    print(f"{WHITE} RECENT BUILD LOG (tail {lines}){RESET}")
    print(f"{DIM}{SUBDIV_49}{RESET}")
    for line in content[-lines:]:
        print(line)
    print(f"{DIM}{SUBDIV_49}{RESET}")


def cmd_web_server(action: str = "menu") -> None:
    """Invoke the server manager for the Flask web UI."""
    server_mgr = SUITE_DIR / "server_manager.py"
    if not server_mgr.exists():
        print(f"{RED}[✗] server_manager.py not found at {server_mgr}{RESET}")
        return
    import subprocess
    cmd = [sys.executable, str(server_mgr), action]
    subprocess.run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="android_compiler",
        description="CLI Android Compiler with Target Chamber Selection & Flask Wrapper",
    )

    # Positional command shortcut
    parser.add_argument(
        "action",
        nargs="?",
        default=None,
        choices=["list", "target", "show", "clear", "build", "debug", "release", "compile", "clean", "install", "log", "web", "status"],
        help="Direct action command",
    )

    # Phase 1 & 2: Chamber selection flags
    parser.add_argument("-l", "--list", action="store_true", help="List available Android targets")
    parser.add_argument("-t", "--target", metavar="TARGET", help="Lock target project into chamber (by index, name, or path)")
    parser.add_argument("-s", "--show-target", action="store_true", help="Show currently loaded chamber target")
    parser.add_argument("-c", "--clear", action="store_true", help="Clear loaded chamber target")

    # Phase 3: Execution actions on loaded target
    parser.add_argument("-b", "--build", action="store_true", help="Build Debug APK (assembleDebug)")
    parser.add_argument("-r", "--release", action="store_true", help="Build Release APK (assembleRelease)")
    parser.add_argument("--compile", action="store_true", help="Compile Debug Sources")
    parser.add_argument("--clean", action="store_true", help="Clean Gradle build cache")
    parser.add_argument("-i", "--install", action="store_true", help="Install compiled APK on device")
    parser.add_argument("--log", action="store_true", help="View recent build log")

    # Phase 4: Web UI dispatch
    parser.add_argument("-w", "--web", action="store_true", help="Launch Flask web interface manager")
    parser.add_argument("--server-status", action="store_true", help="Show web server status")

    args = parser.parse_args()

    chamber = TargetChamber()
    engine = CompilerEngine()

    print_banner()

    # Handle explicit positional action
    pos_action = args.action
    if pos_action == "list" or args.list:
        cmd_list(chamber)
        return 0
    elif pos_action == "show" or args.show_target or pos_action == "status":
        cmd_show_target(chamber)
        return 0
    elif pos_action == "clear" or args.clear:
        cmd_clear_target(chamber)
        return 0
    elif pos_action == "target":
        if not args.target:
            print(f"{RED}[✗] Provide a target argument: android_compiler target <name>{RESET}")
            return 1
        cmd_load_target(chamber, args.target)
        return 0
    elif args.target:
        cmd_load_target(chamber, args.target)
        return 0
    elif pos_action in ("build", "debug") or args.build:
        return cmd_execute_action(chamber, engine, "debug")
    elif pos_action == "release" or args.release:
        return cmd_execute_action(chamber, engine, "release")
    elif pos_action == "compile" or args.compile:
        return cmd_execute_action(chamber, engine, "compile")
    elif pos_action == "clean" or args.clean:
        return cmd_execute_action(chamber, engine, "clean")
    elif pos_action == "install" or args.install:
        return cmd_install(engine)
    elif pos_action == "log" or args.log:
        cmd_view_log(engine)
        return 0
    elif pos_action == "web" or args.web:
        cmd_web_server("menu")
        return 0
    elif args.server_status:
        cmd_web_server("status")
        return 0

    # Default if no flag/action given: show loaded target and brief usage
    cmd_show_target(chamber)
    print(f"\n{WHITE}Quick Commands:{RESET}")
    print(f"  {CYAN}android_compiler.py --list{RESET}            Scan & list targets")
    print(f"  {CYAN}android_compiler.py -t <id|name>{RESET}       Lock target into chamber")
    print(f"  {CYAN}android_compiler.py --build{RESET}            Build loaded target (Debug APK)")
    print(f"  {CYAN}android_compiler.py --release{RESET}          Build loaded target (Release APK)")
    print(f"  {CYAN}android_compiler.py --install{RESET}          Install APK on device")
    print(f"  {CYAN}android_compiler.py --web{RESET}              Launch Flask Web Manager")
    print(f"{RED}{DIVIDER_49}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
