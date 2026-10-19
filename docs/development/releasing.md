# Releasing

A release is a tag. `.github/workflows/release.yml` builds and checks everything and publishes the GitHub release; the
desktop apps find it through the in-app update.

## Versions

- **One version number** (semver) for the product and both OpenCRAVAT modules
  ([ADR 0014](../decisions/0014-one-version-number.md)): `pyproject.toml` `version`, `version:` and a `release_note` entry in
  `modules/webapps/clinreport/clinreport.yml` and `modules/webviewerwidgets/wgclinreport/wgclinreport.yml`.
  `tests/packaging/test_build.py` fails if they differ.
- **Tags:** `vX.Y.Z` for a release, `vX.Y.Z-rcN` for a pre-release. The tag's `X.Y.Z` must equal `pyproject.toml`'s
  version (the workflow checks it), so `v3.1.0-rc1` … `v3.1.0-rc3` and then `v3.1.0` all come from one version bump.
- **Pre-releases** are published as GitHub pre-releases; desktop apps offer them only when «Предлагать предварительные
  версии» is on (Настройки → Запуск). Use them to test the update path before the real release.

## Steps

1. Bump the version in the three files above; move the `[Unreleased]` entries in `CHANGELOG.md` into a
   `## [X.Y.Z] - YYYY-MM-DD` section (`release.yml` uses that section as the release notes).
2. `python -m pytest`, `ruff check .`, a local build and the manual checklist in [testing.md](testing.md) for anything the
   release touches (installer, update, macOS).
3. Merge into `master`; tag the merge commit and push the tag:

   ```text
   git tag -a v3.1.0-rc1 -m "ClinReport 3.1.0-rc1"
   git push origin v3.1.0-rc1
   ```

4. Watch the Release workflow: Version → CI (lint, tests, three desktop builds with smoke tests, installers) and
   Extension zip → GitHub release. Its files: `ClinReport-X-windows-x64.exe`, `ClinReport-X-macos-arm64.dmg`,
   `ClinReport-X-macos-x64.dmg`, `clinreport-extension-X.zip`.
5. Install the pre-release over the previous version (and update to it from inside the app); when it is good, tag
   `vX.Y.Z` on the same commit.

Running Release by hand (Actions → Release → Run workflow) builds everything as `0.0.0-manual.N` and publishes nothing —
a dry run.

## If a release is bad

Do not move or reuse a tag (apps that already updated would not see the fix). Mark the GitHub release as pre-release or
delete it so apps stop offering it, fix, and release the next patch version. Installing an older setup over a newer
version works (same AppId), and user data is untouched either way.

## CI on every push

`.github/workflows/ci.yml`: ruff; pytest on Linux and Windows with a coverage report; the desktop bundle on
`windows-latest`, `macos-15` (arm64) and `macos-15-intel` with `--headless` HTTP checks, the window self-test and the
installer/disk image as 14-day artifacts — so every branch can be tried before it is merged. Dependabot proposes updates
of the actions (weekly) and of the pip requirements (monthly); `open-cravat` is bumped by hand
([packaging.md](packaging.md#the-pinned-stack--packagingstacktoml)).
