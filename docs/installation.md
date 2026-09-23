# Installation on Ubuntu 24.04

## Preparation

Use a dedicated Ubuntu 24.04 x86-64/ARM64 server with root or sudo and working access to Ubuntu repositories, Docker's official apt repository, GitHub, Docker Hub, PyPI and npm. Allow SSH. Public deployments also need a domain pointing to this server and open TCP 80/443. Existing software using these ports must be accounted for before assigning a domain. The installer does not change your firewall or remove existing packages.

The one-command installer requires a published `main` branch:

```bash
curl -fsSL https://raw.githubusercontent.com/farstar-team/farstar_nexa/main/installer.sh | sudo bash
```

For a reviewable download, save that URL to a file, inspect it and run `sudo bash installer.sh`. The bootstrap clones the official repository. Until the initial source is published, the remote installation command is unavailable.

The installer checks root, Ubuntu version and architecture; takes an installation lock; installs prerequisites and Docker Compose when needed; generates secrets; sets up persistence; builds services; runs migrations and readiness checks; asks for the first owner; installs the global CLI and systemd agent. Interactive input comes from `/dev/tty`, so piping the installer does not swallow account prompts. Do not use a headless terminal for initial setup.

## Files and ownership

| Path | Purpose |
| --- | --- |
| `/opt/farstarnexa/releases/` | Immutable release source directories |
| `/opt/farstarnexa/current` | Symlink to the selected release |
| `/etc/farstarnexa/nexa.env` | Root-only configuration and key ring |
| `/var/lib/farstarnexa/postgres` | Database files |
| `/var/lib/farstarnexa/redis` | Redis persistence |
| `/var/lib/farstarnexa/proxy` | Caddy configuration |
| `/var/lib/farstarnexa/caddy-data`, `caddy-config` | Managed TLS state |
| `/var/lib/farstarnexa/backups` | Root-managed backup archives; app read access only |
| `/var/lib/farstarnexa/operations` | Signed operation requests and sanitized progress |
| `/var/lib/farstarnexa/operation-receipts` | Root-only operation replay markers |

Re-running installation retains these directories and the existing environment. A partial first installation can be rerun. Do not rerun it to update application code: use release updates. Container restart policies and the enabled Docker/systemd services provide reboot startup; verify this on the target server before accepting production traffic.

## First login without a domain

The installer defaults to `MOCK_MODE=false`, loopback-only ports and an explicit development environment. On your own computer open an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 root@SERVER_IP
```

Keep it open and visit `http://localhost:8080`. Sign in using the username and password entered in the installer. HTTP is confined to loopback; SSH protects the remote transport. Do not publish port 8080 to the internet.

To test mock messages, use `sudoedit /etc/farstarnexa/nexa.env`, set `MOCK_MODE=true`, and run `sudo farstarnexa apply-config`. The panel displays حالت آزمایشی. Production configuration refuses to start with mock mode or insecure cookies. Domain activation switches mock mode off.

## Verification checklist

Check `sudo farstarnexa status` and `sudo farstarnexa doctor`. Verify first login, account registration, user enable/disable, mock account/rule/message/inbox workflow, backup/restore on disposable data, data survival across `docker compose down`, and restart after a server reboot. Record actual results in the release acceptance report. Application unit tests do not replace these checks.
