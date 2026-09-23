import json
import shutil
import socket
import ssl
import urllib.request
from datetime import UTC, datetime

import backups
from nexa_ops.protocol import DOMAIN, RELEASE

import runtime as rt


def check_update():
    request = urllib.request.Request(
        "https://api.github.com/repos/farstar-team/farstar_nexa/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Farstar-Nexa"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        tag = data["tag_name"]
        if not RELEASE.fullmatch(tag):
            raise ValueError("Invalid release tag")
        return {"installed": rt.version(), "latest": tag, "url": data["html_url"]}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "installed": rt.version(),
                "latest": None,
                "status": "no_published_release",
            }
        raise RuntimeError("Release check failed") from None


def update(tag: str):
    if not RELEASE.fullmatch(tag):
        raise ValueError("Expected a versioned release tag, for example v0.1.1")
    target_version = tuple(map(int, tag[1:].split(".")))
    if target_version <= tuple(map(int, rt.version().split("."))):
        raise ValueError("Updates require a newer version")
    rt.disk_space()
    rt.progress("downloading")
    target = rt.ROOT / "releases" / tag
    if target.exists():
        raise RuntimeError("Release directory already exists; inspect it before retrying")
    rt.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            tag,
            "https://github.com/farstar-team/farstar_nexa.git",
            str(target),
        ]
    )
    if (target / "VERSION").read_text().strip() != tag[1:]:
        raise ValueError("Release version mismatch")
    # Build before downtime; never replace an existing release in place.
    rt.progress("building")
    rt.compose("build", source=target)
    safety = backups.backup(restart=False)
    previous = rt.release()
    try:
        rt.progress("migrating")
        rt.compose("run", "--rm", "migrate", source=target)
        rt.progress("restarting")
        rt.compose("up", "-d", "--remove-orphans", source=target)
        rt.progress("health")
        # Health needs to target the new Compose definition even before switching the symlink.
        import time

        for attempt in range(45):
            try:
                rt.compose(
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=3)",
                    source=target,
                )
                break
            except RuntimeError:
                if attempt == 44:
                    raise
                time.sleep(2)
        temporary = rt.ROOT / "current.next"
        temporary.symlink_to(target, target_is_directory=True)
        temporary.replace(rt.ROOT / "current")
        return {"version": tag[1:], "safety_backup": safety}
    except Exception:
        rt.compose("stop", "api", "worker", source=target)
        raise RuntimeError(
            f"Update failed; writers stopped. Previous code: {previous.name}. "
            f"Safety backup: {safety}. See docs/operations.md for explicit recovery."
        ) from None


def domain(value: str):
    original = rt.CONFIG.read_bytes()
    if value == "remove":
        values = {
            "BASE_URL": "http://localhost:8080",
            "CADDY_SITE": ":80",
            "HTTP_BIND": "127.0.0.1:8080",
            "HTTPS_BIND": "127.0.0.1:8443",
            "COOKIE_SECURE": "false",
            "ENVIRONMENT": "development",
            "MOCK_MODE": "false",
        }
    else:
        if not DOMAIN.fullmatch(value):
            raise ValueError("Invalid DNS domain")
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(value, 443, type=socket.SOCK_STREAM)})
        if not addresses:
            raise ValueError("Domain does not resolve")
        values = {
            "BASE_URL": "https://" + value,
            "CADDY_SITE": value,
            "HTTP_BIND": "0.0.0.0:80",
            "HTTPS_BIND": "0.0.0.0:443",
            "COOKIE_SECURE": "true",
            "ENVIRONMENT": "production",
            "MOCK_MODE": "false",
        }
    rt.save_environment(values)
    try:
        rt.compose("up", "-d", "--force-recreate", "api", "worker", "proxy")
        rt.health()
        if value != "remove":
            rt.compose(
                "exec",
                "-T",
                "proxy",
                "caddy",
                "validate",
                "--config",
                "/etc/caddy/Caddyfile",
            )
    except Exception:
        rt.CONFIG.write_bytes(original)
        rt.CONFIG.chmod(0o600)
        rt.compose("up", "-d", "--force-recreate", "api", "worker", "proxy")
        raise
    telegram = rt.environment().get("TELEGRAM_BOT_TOKEN")
    if telegram and value != "remove":
        rt.compose("exec", "-T", "api", "python", "-m", "nexa.manage", "telegram-webhook")
    return {
        "base_url": values["BASE_URL"],
        "meta_action": "Update the Meta callback and webhook URLs in your app dashboard",
        "telegram_action": "Disable the old webhook when removing a domain"
        if value == "remove"
        else "configured_if_enabled",
    }


def diagnostics():
    config = rt.environment()
    host = config.get("CADDY_SITE", "")
    result = {
        "version": rt.version(),
        "base_url": config.get("BASE_URL"),
        "domain": host,
        "disk_free_bytes": shutil.disk_usage(rt.DATA).free,
        "checked_at": datetime.now(UTC).isoformat(),
        "ssl": {"status": "not_configured"},
        "dns": [],
        "server_addresses": rt.run(["hostname", "-I"]).decode().strip().split(),
    }
    try:
        services = rt.compose("ps", "--format", "json").decode().strip()
        parsed = (
            json.loads(services)
            if services.startswith("[")
            else [json.loads(line) for line in services.splitlines()]
        )
        result["services"] = [
            {
                "service": r.get("Service"),
                "state": r.get("State"),
                "health": r.get("Health"),
            }
            for r in parsed
        ]
    except (ValueError, RuntimeError):
        result["services"] = []
    if DOMAIN.fullmatch(host):
        try:
            result["dns"] = sorted({r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
            with socket.create_connection((host, 443), timeout=5) as sock:
                with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as secure:
                    certificate = secure.getpeercert()
                    result["ssl"] = {
                        "status": "valid",
                        "issuer": str(certificate["issuer"]),
                        "expires": certificate["notAfter"],
                        "renewal": "automatic_caddy",
                    }
        except (OSError, ValueError):
            result["ssl"] = {"status": "unavailable"}
    return result


def execute(action: str, argument: str):
    if action == "backup":
        return {"backup": backups.backup()}
    if action == "restore":
        return backups.restore(argument)
    if action == "delete-backup":
        path = rt.DATA / "backups" / argument
        if path.is_symlink():
            raise ValueError("Invalid backup")
        path.unlink()
        path.with_name(path.name + ".json").unlink(missing_ok=True)
        return {"deleted": argument}
    if action == "domain":
        return domain(argument)
    if action == "update":
        return update(argument)
    if action == "check-update":
        return check_update()
    if action == "ssl":
        rt.compose(
            "exec",
            "-T",
            "proxy",
            "caddy",
            "reload",
            "--config",
            "/etc/caddy/Caddyfile",
            "--force",
        )
    return diagnostics()
