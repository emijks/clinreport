# 004 · Store unreachable through the VPN; code-only hg38 / wgnote on the dev machine

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P3 | environment | `C:\open-cravat\modules` on the dev machine |

## Problem

**Cause (found 2026-09-25): the lab VPN.** With the VPN on, `https://store.opencravat.org` (162.129.223.26) resolves but every
connection times out, so `oc module install-base` / `oc module install …` fail; with the VPN off the Store works (the user installed
the base set through the GUI of the Docker server that way). Two base modules are required for the workflow:

- `hg38` (mapper): the viewer dereferences the result's mapper module when building columns (`cravat_report.py:792-796`);
  without it the viewer spins forever.
- `wgnote` (webviewerwidget): the only way to edit Notes in the viewer.

Workaround applied: **code-only copies** from `https://github.com/KarchinLab/open-cravat-modules-karchinlab` (master) into
`C:\open-cravat\modules\mappers\hg38` (no gene database — fine for viewing; `oc run` would fail) and
`C:\open-cravat\modules\webviewerwidgets\wgnote` (complete; the widget has no data). Commands in
[setup](../../development/setup.md#from-scratch-windows). These are GitHub **master** versions, not necessarily
what a 2.2.9 Store install would pick (wgnote 3.0.0 falls back to `base__note`, so behaviour is the same for 2.2.9 results).

## TODO

- [ ] When the Store is reachable (other network/VPN), replace the copies: `oc module install hg38 wgnote -y` (or `install-base`).
- [ ] Do not ship the code-only copies to clinicians.

## Acceptance

Dev machine uses Store-installed base modules, or this note stays as the documented workaround.
