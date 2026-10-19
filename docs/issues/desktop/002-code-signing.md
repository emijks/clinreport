# 002 · Desktop app is not code-signed

| Status | Priority |
|---|---|
| open — decided for 3.0: unsigned ([ADR 0012](../../decisions/0012-unsigned-builds.md)); revisit with a certificate | P2 |

- **Windows SmartScreen** warns about the unsigned installer («Подробнее» → «Выполнить в любом случае»).
- **Windows Smart App Control** (on by default on some fresh Windows 11 installs) blocks unsigned DLLs inside the bundle
  (Python packages' `.pyd`/`.dll`); it was seen blocking numpy/pandas on the dev machine. The only fixes are turning it off
  (irreversible without reinstalling Windows) or signing every binary.
- **macOS Gatekeeper**: the app is ad-hoc signed only; users right-click → «Открыть» once, or `xattr -cr`. Notarisation needs
  an Apple Developer ID (99 USD/year).

Installers built on the dev machine never show the SmartScreen prompt: only downloaded files carry the "from the
internet" mark (Mark of the Web) that SmartScreen checks. Test with a file downloaded from GitHub.

## Options (researched 2026-10-19)

| Option | Cost | Fit |
|---|---|---|
| [SignPath Foundation](https://signpath.org) | free for open-source projects | The repository is public and open source, so it qualifies. OV certificate; the key stays in SignPath's HSM; a GitHub Action (`signpath/github-action-submit-signing-request`) submits the CI build, and SignPath checks it came from this repository. Needs an application and a manual approval per release. Example: [Super Productivity](https://super-productivity.com/code-signing/). |
| [Azure Artifact Signing](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) (formerly Trusted Signing) | ~10 USD/month | GA since January 2026; GitHub Action available. Public trust only for organisations in the US/Canada/EU/UK and individuals in the US/Canada. |
| Apple Developer ID + notarisation | 99 USD/year | The only way to remove the Gatekeeper prompt on macOS. |

Signing does not remove SmartScreen at once: since 2024 EV certificates no longer skip it either, and reputation builds
up with downloads of files signed by the same identity.

## TODO

- [ ] Apply to SignPath Foundation (Windows; sign the `.exe`/`.dll`/`.pyd` in the bundle and the installer).
- [ ] Decide on an Apple Developer ID (sign + notarise the `.app`).
- [ ] build.py / ci.yml: sign step per platform before packaging, skipped while the secrets are missing; keep secrets in
      CI variables only.

## Acceptance

Installers start without security prompts on a default Windows 11 and macOS.
