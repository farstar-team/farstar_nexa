import contextlib
import hmac
import io
import json
import os
import sys
import time
import uuid

import operations
import runtime as rt
from nexa_ops.protocol import atomic_json, sign, validate_operation


class ProgressWriter(io.TextIOBase):
    def __init__(self, path, result):
        self.path, self.result = path, result

    def write(self, value):
        try:
            stage = json.loads(value).get("stage")
            if stage:
                self.result["stage"] = stage
                atomic_json(self.path, self.result)
        except (ValueError, AttributeError):
            pass
        return len(value)


def process(path):
    identity = path.name.removesuffix(".request.json")
    if str(uuid.UUID(identity)) != identity or path.is_symlink() or path.stat().st_size > 8192:
        raise ValueError("Invalid operation request")
    result_path = path.with_name(identity + ".result.json")
    if result_path.exists():
        path.unlink()
        return
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        data = json.loads(source.read(8193))
    payload = data["payload"]
    if payload["id"] != identity or not hmac.compare_digest(
        data["signature"], sign(payload, rt.environment()["SECRET_KEY"])
    ):
        raise ValueError("Invalid operation signature")
    if not -30 <= time.time() - float(payload["created_at"]) <= 300:
        raise ValueError("Expired operation request")
    validate_operation(payload["action"], payload["argument"], payload["confirmed"])
    receipts = rt.DATA / "operation-receipts"
    receipts.mkdir(mode=0o700, exist_ok=True)
    # The web process cannot delete this replay marker or make an operation eligible again.
    receipt_fd = os.open(receipts / identity, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(receipt_fd)
    result = {
        "id": identity,
        "action": payload["action"],
        "status": "running",
        "stage": "starting",
    }
    atomic_json(result_path, result)
    # Claim once before executing; a daemon crash requires operator review, never automatic replay.
    path.unlink()
    try:
        with contextlib.redirect_stdout(ProgressWriter(result_path, result)):
            result["result"] = operations.execute(payload["action"], payload["argument"])
        result["status"], result["stage"] = "complete", "complete"
    except Exception as exc:
        result["status"], result["stage"] = "failed", "failed"
        result["error"] = type(exc).__name__
        result["recovery"] = (
            "Inspect farstarnexa doctor and docs/operations.md; do not retry a restore blindly."
        )
    atomic_json(result_path, result)


def main():
    import fcntl

    folder = rt.DATA / "operations"
    started_from = rt.release()
    last = 0
    while True:
        if time.time() - last > 30:
            try:
                atomic_json(folder / "host-status.json", operations.diagnostics())
            except Exception:
                pass
            last = time.time()
        for request in folder.glob("*.request.json"):
            with (rt.DATA / "operation.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    process(request)
                except Exception:
                    request.rename(request.with_suffix(".rejected"))
        time.sleep(2)
        if rt.release() != started_from:
            os.execv(sys.executable, [sys.executable, str(rt.release() / "cli/main.py"), "agent"])
