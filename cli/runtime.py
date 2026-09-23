import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(os.environ.get("NEXA_ROOT", "/opt/farstarnexa"))
DATA = Path(os.environ.get("NEXA_DATA", "/var/lib/farstarnexa"))
CONFIG = Path(os.environ.get("NEXA_CONFIG", "/etc/farstarnexa/nexa.env"))


def release() -> Path:
    return (ROOT / "current").resolve()


def version() -> str:
    return (release() / "VERSION").read_text().strip()


def environment() -> dict[str, str]:
    result = {}
    for line in CONFIG.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            key, value = line.split("=", 1)
            result[key] = value
    return result


def save_environment(values: dict[str, str]):
    existing = environment()
    existing.update(values)
    if any("\n" in v or "\r" in v for v in existing.values()):
        raise ValueError("Newlines are not valid configuration values")
    temp = CONFIG.with_suffix(".tmp")
    temp.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    temp.chmod(0o600)
    temp.replace(CONFIG)


def run(args, *, capture=True, input_data=None, cwd=None):
    result = subprocess.run(
        args,
        input=input_data,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        cwd=cwd,
        check=False,
    )
    if result.returncode:
        # Do not forward command arguments, environment, URLs or output into the web operation log.
        raise RuntimeError(
            f"Command failed ({Path(str(args[0])).name}, exit {result.returncode}); use CLI diagnostics"
        )
    return result.stdout or b""


def compose(*args, source=None, capture=True, input_data=None):
    source = source or release()
    env = dict(
        os.environ,
        NEXA_ENV_FILE=str(CONFIG),
        NEXA_RELEASE=(source / "VERSION").read_text().strip(),
    )
    command = [
        "docker",
        "compose",
        "--project-name",
        "farstarnexa",
        "--env-file",
        str(CONFIG),
        "--project-directory",
        str(source),
        "-f",
        str(source / "docker-compose.yml"),
        *args,
    ]
    result = subprocess.run(
        command,
        env=env,
        input=input_data,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Compose operation failed; run farstarnexa logs or doctor")
    return result.stdout or b""


def health():
    for _ in range(45):
        try:
            compose(
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=3)",
            )
            return
        except RuntimeError:
            time.sleep(2)
    raise RuntimeError("Readiness check failed; services retained for diagnosis")


def disk_space():
    used = sum(p.stat().st_size for p in (DATA / "postgres").rglob("*") if p.is_file())
    if shutil.disk_usage(DATA).free < max(2 * used, 2 * 1024**3):
        raise RuntimeError("Insufficient disk space: need twice database size or at least 2 GiB free")


def progress(stage: str):
    print(json.dumps({"stage": stage}), flush=True)
