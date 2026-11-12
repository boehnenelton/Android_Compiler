#!/data/data/com.termux/files/usr/bin/env python3
"""
# Name:           server_manager.py
# Description:    Async background server lifecycle manager for android_compiler Flask app
# Version:        100
# Date Created:   2026-11-12
# Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
# License:        PolyForm-Noncommercial-1.0.0
# RELATIONAL_ID:  android-compiler-server-001
"""

from __future__ import annotations
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_PATH: Path = Path(__file__).resolve()
APP_DIR: Path = SCRIPT_PATH.parent
APP_PY: Path = APP_DIR / "app.py"
PID_FILE: Path = APP_DIR / ".server.pid"
LOG_FILE: Path = APP_DIR / "server.log"

PYTHON: str = sys.executable

DEFAULT_PORT: int = 8450
DEFAULT_HOST: str = "127.0.0.1"

# ─── ANSI (49-col mobile portrait ceiling) ────────────────────────────────────
RED = "\033[38;2;222;38;38m"
WHITE = "\033[1;37m"
DIM = "\033[0;37m"
RESET = "\033[0m"
DIV = "=" * 49
SUB = "-" * 49


def print_ok(msg: str) -> None:
    print(f"{WHITE}[✓] {msg.lower()}{RESET}")


def print_fail(msg: str) -> None:
    print(f"{RED}[✗] {msg.upper()}{RESET}", file=sys.stderr)


def read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except ValueError:
            pass
    return None


def is_running(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def start(host: str, port: int) -> None:
    pid = read_pid()
    if is_running(pid):
        print_fail(f"server already running on pid {pid}")
        return

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_FILE, "a", encoding="utf-8")

    proc = subprocess.Popen(
        [PYTHON, str(APP_PY), "--host", host, "--port", str(port)],
        stdout=log_fh,
        stderr=log_fh,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    time.sleep(1.2)

    url = f"http://localhost:{port}"
    print_ok(f"server started — pid {proc.pid}")
    print_ok(f"url: {url}")

    # Copy URL to Termux clipboard
    try:
        subprocess.run(
            ["termux-clipboard-set", url],
            timeout=3, check=False, capture_output=True,
        )
        print_ok("url copied to clipboard")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Launch Chrome via Android Activity Manager
    try:
        subprocess.run(
            ["am", "start", "-n",
             "com.android.chrome/com.google.android.apps.chrome.Main",
             "-d", url],
            timeout=4, check=False, capture_output=True,
        )
        print_ok("chrome launched")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            subprocess.run(["termux-open-url", url],
                           timeout=4, check=False, capture_output=True)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            try:
                subprocess.run(["termux-open", url],
                               timeout=4, check=False, capture_output=True)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass


def stop() -> None:
    pid = read_pid()
    if not is_running(pid):
        print_fail("no server running")
        PID_FILE.unlink(missing_ok=True)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        time.sleep(0.6)
        if is_running(pid):
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        PID_FILE.unlink(missing_ok=True)
        print_ok("server stopped")
    except Exception as exc:
        print_fail(f"stop failed: {exc}")


def status_banner(port: int) -> None:
    pid = read_pid()
    running = is_running(pid)
    state = f"{WHITE}RUNNING{RESET}" if running else f"{RED}STOPPED{RESET}"
    pid_str = str(pid) if running else "—"
    url = f"http://localhost:{port}" if running else "—"
    print(f"{DIM}{DIV}{RESET}")
    print(f" {RED}ANDROID COMPILER WEB SERVER{RESET}")
    print(f"{DIM}{SUB}{RESET}")
    print(f" {RED}Status:{RESET}  {state}")
    print(f" {RED}PID:{RESET}     {DIM}{pid_str}{RESET}")
    print(f" {RED}URL:{RESET}     {DIM}{url}{RESET}")
    print(f" {RED}Log:{RESET}     {DIM}{LOG_FILE.name}{RESET}")
    print(f"{DIM}{DIV}{RESET}")


def tail_log(lines: int = 30) -> None:
    if not LOG_FILE.exists():
        print_fail("no server.log yet")
        return
    all_lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in all_lines[-lines:]:
        print(line)


def tui_menu(host: str, port: int) -> None:
    while True:
        status_banner(port)
        print(f"{DIM}{SUB}{RESET}")
        print(f"  [{RED}1{RESET}] {WHITE}Start{RESET}")
        print(f"  [{RED}2{RESET}] {WHITE}Stop{RESET}")
        print(f"  [{RED}3{RESET}] {WHITE}Restart{RESET}")
        print(f"  [{RED}4{RESET}] {WHITE}View log (last 30){RESET}")
        print(f"  [{RED}5{RESET}] {WHITE}Refresh status{RESET}")
        print(f"  [{RED}0{RESET}] {WHITE}Exit{RESET}")
        print(f"{DIM}{DIV}{RESET}")
        try:
            choice = input(f"{RED}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if choice == "1":
            start(host, port)
        elif choice == "2":
            stop()
        elif choice == "3":
            stop()
            time.sleep(0.5)
            start(host, port)
        elif choice == "4":
            tail_log()
        elif choice == "5":
            pass
        elif choice == "0":
            break
        else:
            print_fail("unknown option")


def main() -> int:
    parser = argparse.ArgumentParser(prog="server_manager")
    parser.add_argument("command", nargs="?", default="menu",
                        choices=["start", "stop", "restart", "status", "log", "menu"])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args()

    if args.command == "start":
        start(args.host, args.port)
    elif args.command == "stop":
        stop()
    elif args.command == "restart":
        stop()
        time.sleep(0.5)
        start(args.host, args.port)
    elif args.command == "status":
        status_banner(args.port)
    elif args.command == "log":
        tail_log()
    else:
        tui_menu(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
