# 002 · Desktop app is not code-signed

| Status | Priority |
|---|---|
| open — decided for 3.0: unsigned ([ADR 0010](../../decisions/0012-unsigned-builds.md)); revisit with a certificate | P2 |

- **Windows SmartScreen** warns about the unsigned installer («Подробнее» → «Выполнить в любом случае»).
- **Windows Smart App Control** (on by default on some fresh Windows 11 installs) blocks unsigned DLLs inside the bundle
  (Python packages' `.pyd`/`.dll`); it was seen blocking numpy/pandas on the dev machine. The only fixes are turning it off
  (irreversible without reinstalling Windows) or signing every binary.
- **macOS Gatekeeper**: the app is ad-hoc signed only; users right-click → «Открыть» once, or `xattr -cr`. Notarisation needs
  an Apple Developer ID (99 USD/year).

## TODO

- [ ] Decide: Azure Trusted Signing (Windows; signs `.exe`/`.dll`/`.pyd` in the bundle and the installer) and/or an Apple
      Developer ID (sign + notarise the `.app`).
- [ ] build.py: sign step per platform before packaging; keep secrets in CI variables only.

## Acceptance

Installers start without security prompts on a default Windows 11 and macOS.
