#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import operations
import runtime as rt
from nexa_ops.protocol import validate_operation

MENU = [
    "Status",
    "Start Services",
    "Stop Services",
    "Restart Services",
    "Update Farstar Nexa",
    "Backup",
    "Restore Backup",
    "Domain Management",
    "SSL Management",
    "Admin Management",
    "View Logs",
    "System Diagnostics",
    "Repair Installation",
    "Configuration",
    "Uninstall",
]
COMMANDS = [
    "status",
    "start",
    "stop",
    "restart",
    "update",
    "backup",
    "restore",
    "domain",
    "ssl",
    "admin",
    "logs",
    "doctor",
    "repair",
    "config",
    "uninstall",
]


def interactive():
    while True:
        print(
            "\n========================================\n     FARSTAR NEXA — Server Manager\n========================================"
        )
        for index, title in enumerate(MENU, 1):
            print(f"{index:2}. {title}")
        print(" 0. Exit")
        selected = input("> ").strip()
        if selected == "0":
            return
        if not selected.isdigit() or not 1 <= int(selected) <= len(COMMANDS):
            continue
        action = COMMANDS[int(selected) - 1]
        argument = ""
        if action in {"restore", "domain", "update"}:
            argument = input(
                {
                    "restore": "Backup filename: ",
                    "domain": "Domain or remove: ",
                    "update": "Release tag (vX.Y.Z): ",
                }[action]
            ).strip()
        try:
            dispatch(action, argument, False)
        except Exception as exc:
            print(str(exc))


def dispatch(action, argument, confirmed):
    if action in {"restore", "delete-backup", "domain", "update", "uninstall", "stop"} and not confirmed:
        print(
            "This changes the installation. Restore overwrites data; removing a domain restricts access to SSH tunnelling."
        )
        if input(f"Type {action.upper()} to continue: ") != action.upper():
            return
        confirmed = True
    if action in {
        "backup",
        "restore",
        "delete-backup",
        "domain",
        "ssl",
        "update",
        "check-update",
        "diagnostics",
    }:
        import fcntl

        validate_operation(action, argument, confirmed)
        with (rt.DATA / "operation.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            print(json.dumps(operations.execute(action, argument), indent=2))
    elif action == "status":
        print("Farstar Nexa " + rt.version())
        rt.compose("ps", capture=False)
    elif action in {"start", "restart", "repair"}:
        if action == "repair":
            rt.compose("config", "--quiet")
            rt.compose("build")
            rt.compose("run", "--rm", "migrate")
        rt.compose(*(["restart"] if action == "restart" else ["up", "-d"]), capture=False)
        rt.health()
    elif action == "stop":
        rt.compose("stop", capture=False)
    elif action == "logs":
        rt.compose("logs", "--tail", "150", capture=False)
    elif action == "doctor":
        print(json.dumps(operations.diagnostics(), indent=2))
    elif action == "admin":
        command = argument or input("create-admin or reset-password: ")
        if command not in {"create-admin", "reset-password"}:
            raise ValueError("Invalid admin command")
        rt.compose("exec", "api", "python", "-m", "nexa.manage", command, capture=False)
    elif action == "telegram-webhook":
        rt.compose(
            "exec",
            "-T",
            "api",
            "python",
            "-m",
            "nexa.manage",
            "telegram-webhook",
            capture=False,
        )
    elif action == "config":
        print(
            f"Private configuration: {rt.CONFIG}\nUse sudoedit to edit it, then run farstarnexa apply-config."
        )
    elif action == "apply-config":
        rt.compose("up", "-d", "--force-recreate", "api", "worker", "proxy", capture=False)
        rt.health()
    elif action == "uninstall":
        rt.compose("down", capture=False)
        rt.run(["systemctl", "disable", "--now", "farstarnexa-agent.service"])
        print(
            f"Services stopped. All data, backups, configuration and source retained in {rt.DATA}, {rt.CONFIG}, {rt.ROOT}."
        )
    else:
        raise ValueError("Unknown command")


def main():
    parser = argparse.ArgumentParser(prog="farstarnexa")
    parser.add_argument("command", nargs="?")
    parser.add_argument("argument", nargs="?", default="")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Explicit confirmation for a disruptive operation",
    )
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0:
        raise SystemExit("Run this server manager with sudo on Ubuntu 24.04.")
    if args.command == "agent":
        import agent

        agent.main()
    elif args.command:
        dispatch(args.command, args.argument, args.yes)
    else:
        interactive()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
