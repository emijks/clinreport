# Issues

Open work and known problems, one file per issue, versioned with the code. An issue's id is `<area>/<number>`, e.g.
`clinreport/019`. Numbers are unique within an area and were kept from GenLab Services and the OpenCRAVAT extension
repository when the issues moved here (3.0.0), so older references still resolve.

| Area | Covers |
|---|---|
| [clinreport/](#clinreport) | the extension: report logic, review page, widget, HTTP API |
| [desktop/](#desktop) | the desktop app: launcher, bundle, installers, updates |
| [server/](#server) | running the extension on a shared server (login mode) |

**Priority:** **P1** before rollout to clinicians / network use · **P2** soon · **P3** nice to have · **P4** minor.
**Status:** `open` · `in progress` · `blocked` (needs a decision or a resource) · `done` · `obsolete`.

## How to work with issues

- Each file has a status/priority table, the problem with evidence, a TODO checklist, acceptance criteria and pointers to
  the code.
- When the status changes, update it in the file **and** in the table below.
- A new issue gets the next free number in its area: `<area>/<NNN>-<short-slug>.md`.
- Done issues stay (their history and links stay valid), marked `done` with a short "Resolution" section.
- A choice that is costly to reverse is not an issue but a [decision](../decisions/README.md); an issue may lead to one.

## Moving to GitHub Issues (planned)

These files will become [GitHub Issues](https://github.com/emijks/clinreport/issues) once the repository's issue tracker is
the place the team works in. Until then the files are the source of truth. When moving:

1. Create one GitHub issue per **open** file (title = the file's title, body = the file; labels `area:<area>`, `P1`…`P4`).
   `gh issue create --title "<title>" --body-file <file> --label area:clinreport,P1` does it per file.
2. Replace the file's body with a link to the GitHub issue (keep the file, so links from code, docs and decisions still
   work), and add the issue number to the table below.
3. Done issues stay here as history; new issues go straight to GitHub.

## clinreport

| # | Title | Priority | Status |
|---|---|---|---|
| [001](clinreport/001-postgres-untested.md) | Postgres upload / «Похожие» never tested against a real server | **P1** | blocked |
| [003](clinreport/003-python-version-constraints.md) | OpenCRAVAT 2.x needs Python < 3.12 and setuptools < 81 | **P1** | open |
| [019](clinreport/019-note-column-base-note-variant.md) | Notes in `base__note_variant` (OC ≥ 2.3.1) are not read | **P1** | open |
| [021](clinreport/021-invalid-notes-silently-ignored.md) | Invalid Note values are silently ignored | **P1** | open |
| [005](clinreport/005-review-edits-not-persisted.md) | Review edits are lost when the page is closed | P2 | open |
| [006](clinreport/006-reprocess-discards-edits.md) | «Обработать» again silently discards edits | P2 | open |
| [009](clinreport/009-interpretation-not-editable.md) | Interpretation paragraphs cannot be seen or edited | P2 | open |
| [011](clinreport/011-inherited-legacy-schema-bugs.md) | Inherited bugs in the legacy-schema bridge | P2 | open |
| [012](clinreport/012-inherited-narrative-bugs.md) | Inherited text defects in the generated report | P2 | open |
| [004](clinreport/004-store-unreachable-dev-machine.md) | Store unreachable through the VPN | P3 | open |
| [008](clinreport/008-save-dialog-manual-test.md) | Native «Сохранить как…» dialog not covered by automation | P3 | open |
| [010](clinreport/010-cnv-mt-str-sections-empty.md) | CNV / MT / STR sections (Notes 4–6) always empty | P3 | open |
| [015](clinreport/015-russian-annotations-online-only.md) | Russian annotations need internet | P3 | open |
| [016](clinreport/016-widget-discoverability.md) | Entry point only on the Summary tab, can be hidden | P3 | open |
| [017](clinreport/017-no-ci.md) | No CI; live tests need a running GUI | P3 | in progress (CI done; synthetic results open) |
| [020](clinreport/020-review-page-parity-gaps.md) | Some rendered fields are not editable | P3 | open |
| [018](clinreport/018-thread-safety.md) | Minor thread-safety gaps in service state | P4 | open |
| [002](clinreport/002-opencravat-3x-untested.md) | OpenCRAVAT 3.x (Flask GUI) support | P3 | done (follow-ups open) |
| [007](clinreport/007-security-dbpath-and-server-mode.md) | Arbitrary local file read; no auth | P2 | done (server follow-ups) |
| [013](clinreport/013-core-copy-divergence.md) | Report core is a copy of the desktop app | P2 | done (3.0.0) |
| [014](clinreport/014-distribution-and-versioning.md) | Distribution, version checks, updates | P2 | done (3.0.0) |

## desktop

| # | Title | Priority | Status |
|---|---|---|---|
| [007](desktop/007-empty-window-macos.md) | The control window is empty on an old Mac | P1 | fixed — to confirm on the Mac |
| [002](desktop/002-code-signing.md) | Desktop app is not code-signed | P2 | open (unsigned for 3.0) |
| [003](desktop/003-lab-modules-tab.md) | The lab's own OpenCRAVAT modules cannot be added in the app | P3 | open — deferred |
| [004](desktop/004-install-into-existing-opencravat.md) | Installing into an existing OpenCRAVAT is manual | P3 | open — deferred |
| [006](desktop/006-upstream-windows-fixes.md) | OpenCRAVAT 3.x needs our start-up patches on Windows | P3 | open |
| [001](desktop/001-build-and-release.md) | Desktop builds are manual; macOS not built | P2 | done (3.0.0) |
| [005](desktop/005-update-check.md) | The app does not tell users about new versions | P3 | done (3.0.0) |

## server

| # | Title | Priority | Status |
|---|---|---|---|
| [002](server/002-multiuser-and-clinreport-hardening.md) | Login mode: ClinReport hardened; server-side hardening open | **P1** before network use | in progress |
