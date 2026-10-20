# ClinReport

Clinical reports (`.docx`) from [OpenCRAVAT](https://opencravat.org) results. The clinician marks variants in
OpenCRAVAT's **Note** column, opens the review window from the result's **Summary** tab, checks and edits the report and
saves it from a Word template — the lab's standard ones (DZM, FND, 10x for LPWGS) or its own.

One code base, three ways to run it:

| | For whom | What you get |
|---|---|---|
| **Desktop app** | a clinician's own computer, Windows or macOS | an installer with OpenCRAVAT, Python and ClinReport inside; nothing else to install, no administrator rights |
| **Extension** | an existing OpenCRAVAT installation (e.g. a lab server) | `install_extension.py` adds the ClinReport modules to it |
| **Command line** | batch jobs, scripts | `launchers/cli/cli.py` writes the same documents without the GUI |

## Install

**Desktop app** — step by step in Russian: [INSTALL.md](INSTALL.md). Download from
[Releases](https://github.com/emijks/clinreport/releases):

- **Windows 10/11, 64-bit:** `ClinReport-<version>-windows-x64.exe`. If SmartScreen warns about an unknown publisher:
  «Подробнее» → «Выполнить в любом случае» (the app is not code-signed).
- **macOS:** `ClinReport-<version>-macos-arm64.dmg` (Apple Silicon, macOS 11+) or `…-macos-x64.dmg` (Intel, macOS 10.15+).
  Drag ClinReport to Applications, then remove the quarantine flag once per installed version (the app is not
  notarised): `xattr -dr com.apple.quarantine /Applications/ClinReport.app`.

**Update:** ClinReport shows «обновить до X» when a new version is out (Windows: one click; macOS: opens the release page),
or install the new version over the old one. Settings, your own templates and OpenCRAVAT jobs are kept — they live in
`%LOCALAPPDATA%\ClinReport` (Windows) or `~/Library/Application Support/ClinReport` (macOS), never in the program folder.

**Extension** — with the Python that runs your OpenCRAVAT (≥ 2.2.9; tested with 3.2.3):

```text
<opencravat python> install_extension.py [--with-db]      # from clinreport-extension-<version>.zip, or packaging/ here
```

Run it again to update; `--uninstall` removes it. Restart `oc gui` afterwards.

## Use

1. Open the result in OpenCRAVAT and mark variants in **Note**: `1` патогенный, `2` вероятно патогенный, `3` ВНЗ,
   `7` не связан с основным диагнозом, `8` носительство.
2. **Summary** tab → **«Открыть окно заключения»** (desktop app: also «Заключение» next to a recent result).
3. Pick the target sample → **«Обработать»** or **«Обработать как LPWGS»**, review the tabs, pick the template,
   **«Сохранить как…»**.

Step-by-step guides in Russian: [desktop app](docs/guides/desktop-app.md), [report templates](docs/guides/templates.md),
[extension](docs/guides/extension.md), [command line](docs/guides/cli.md).

## Develop

```text
pip install -r requirements-dev.txt          # Python 3.13: OpenCRAVAT 3.2.3, the app's dependencies, pytest, ruff
python -m pytest                             # unit, route, CLI, launcher and packaging tests
ruff check .
python packaging/build.py --package          # desktop app + installer for this OS → packaging/dist/
```

Start with [AGENTS.md](AGENTS.md) (also the best overview for people), then [docs/](docs/README.md): architecture,
development, reference and the [decisions](docs/decisions/README.md) behind the design. Every push runs CI on Linux,
Windows and macOS; a tag `vX.Y.Z` publishes a release ([docs/development/releasing.md](docs/development/releasing.md)).
Changes are listed in [CHANGELOG.md](CHANGELOG.md).
