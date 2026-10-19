# 001 · Desktop builds are manual; macOS not built yet

| Status | Priority |
|---|---|
| **done** (3.0.0) — first run on a real Mac still to confirm | P2 |

## Resolution (3.0.0)

GitHub Actions instead of GitLab CI: `ci.yml` builds and checks the bundle on `windows-latest`, `macos-15` (arm64) and
`macos-15-intel` on every push; `release.yml` publishes the installer and both disk images for a tag `vX.Y.Z`
([docs/development/releasing.md](../../development/releasing.md)). Tags are `v*` (not `desktop-v*`). The macOS builds
enforce the oldest supported macOS ([ADR 0011](../../decisions/0011-macos-minimum-versions.md)).

`packaging/build.py --package` must run on each target platform: a Windows PC for the installer, a Mac of each architecture
(Apple Silicon `macos-arm64`, Intel `macos-x64`) for the `.dmg`. There was no CI (GenLab Services had decided on self-hosted GitLab), so a developer built by hand.

Verified so far (2026-10-15, Windows 11, OpenCRAVAT 3.2.3, Python 3.13 bundle): see the checklist in
[docs/desktop.md](../../development/packaging.md#develop-and-test). An earlier Windows build of the same launcher on OpenCRAVAT 2.2.9 / Python 3.11
also passed the installer build. **macOS: never built or run.** Linux (`.tar.gz`, testing only): built and started headless
in a `python:3.12-slim` container for the 2.2.9 variant only.

## TODO

- [ ] Build and run the checklist on a Mac (arm64; x64 if the lab still has Intel Macs). Expect to fix: the `.app` launcher
      script, pywebview/pyobjc, Gatekeeper prompts.
- [ ] GitLab CI: a Windows runner (or a Windows VM) and a macOS runner on the lab network; jobs = build, `tests/desktop`,
      `--headless` + `smoke_http.py` against synthetic results, `--selftest`, `--package`; tag `desktop-vX.Y.Z` → release
      files on the GitLab release page.
- [ ] Version: tag `desktop-vX.Y.Z` (build.py's default `--version` comes from `git describe --match desktop-v*`).

## Acceptance

A tag produces the Windows installer and both macOS disk images after the checks pass on each platform.
