# 005 · The desktop app does not tell users about new versions

| Status | Priority |
|---|---|
| **done** (3.0.0) | P3 |

## Resolution (3.0.0)

Releases are published on GitHub (`emijks/clinreport`, set in `packaging/stack.toml`), so `updates.py` reads them directly.
The window offers «обновить до X»: on Windows it downloads the setup, checks it and installs silently, keeping user data;
on macOS it opens the release page. Pre-releases only when enabled
([ADR 0009](../../decisions/0009-in-app-updates-from-github-releases.md)).

The launcher can show «доступна X.Y» next to its version (`clinreport_desktop/updates.py`), but it only speaks the
GitHub releases API and `packaging/build.py` ships with `UPDATE_REPO = ''` (off), since GenLab Services was moving to self-hosted GitLab.

## TODO

- [ ] When desktop releases are published on GitLab: read `GET /api/v4/projects/<id>/releases` (tags `desktop-v*`) — reachable
      only on the lab network/VPN, which is fine (no answer = no badge).
- [ ] Set the URL in build.py; keep the check silent on failure.

## Acceptance

With a newer release published, the window shows the badge linking to it.
