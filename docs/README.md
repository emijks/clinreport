# ClinReport documentation

Start with the [README](../README.md) (what ClinReport is) and [AGENTS.md](../AGENTS.md) (map, commands, rules). The docs
are organised by what you need ([Diátaxis](https://diataxis.fr)): how-to guides for clinicians, development guides,
reference, and explanation of the design and its decisions.

| | Document | For |
|---|---|---|
| **Explanation** | [architecture.md](architecture.md) + [architecture.drawio.svg](architecture.drawio.svg) | how it fits together, where a change belongs, the invariants |
| | [decisions/](decisions/README.md) | why it is built this way (architecture decision records) |
| **Guides** (Russian, for clinicians) | [../INSTALL.md](../INSTALL.md) | supported systems; install, update, remove the desktop app |
| | [guides/desktop-app.md](guides/desktop-app.md) | use the desktop app |
| | [guides/templates.md](guides/templates.md) | the lab's own report templates |
| | [guides/extension.md](guides/extension.md) | adding ClinReport to an existing OpenCRAVAT |
| | [guides/cli.md](guides/cli.md) | reports from the command line |
| **Development** | [development/setup.md](development/setup.md) | environment, running the extension, edit → see loop, troubleshooting |
| | [development/testing.md](development/testing.md) | test layers, coverage, adding tests, the manual checklist |
| | [development/packaging.md](development/packaging.md) | the desktop bundle, installers, OpenCRAVAT patches, the launcher |
| | [development/releasing.md](development/releasing.md) | versions, tags, the release workflow |
| | [development/extending.md](development/extending.md) | recipes: a template field, a column, an endpoint, a setting |
| **Reference** | [reference/http-api.md](reference/http-api.md) | the review page ↔ server contract |
| | [reference/data-model.md](reference/data-model.md) | Note codes, result columns, the template context, the database |
| | [reference/opencravat-integration.md](reference/opencravat-integration.md) | the OpenCRAVAT extension points we rely on, version matrix |
| | [reference/frontend.md](reference/frontend.md) | the review page's code |
| **Work** | [issues/](issues/README.md) | open problems and planned work (moving to GitHub Issues later) |

Changes per version: [CHANGELOG.md](../CHANGELOG.md).

## Keeping the docs true

- A change that alters behaviour updates the guide or reference page that describes it in the same commit.
- A decision that is costly to reverse gets an ADR ([decisions/README.md](decisions/README.md)); an accepted ADR is not
  edited later — a new one supersedes it.
- Code paths are written as text (`modules/webapps/clinreport/route.py`), so a search finds them after a move.
- The diagram is `architecture.drawio.svg`: edit it in draw.io (desktop app, app.diagrams.net or the VS Code extension
  "Draw.io Integration") — it stays a viewable SVG on GitHub.
