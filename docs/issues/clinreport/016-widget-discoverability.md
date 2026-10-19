# 016 · Entry point only on the Summary tab, can be hidden

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P3 | UX | `wgclinreport.js` |

## Problem

The only in-viewer entry point is the ClinReport card on the **Summary** tab. Clinicians spend their time on the **Variant** tab
(marking Notes). The card can also be closed via the viewer's widget menu and stays hidden in the saved layout.

## Options

- [ ] Also register a `variant`-tab generator (`widgetGenerators.clinreport.variant`) with a compact button — it appears in the
      variant detail panel next to the Note widget, where the clinician already is.
- [ ] Set `default_hidden: false` explicitly / document how to re-enable the widget.
- [ ] (Invasive, avoid) inject a toolbar button into the viewer header from the widget script.
- [ ] Bookmarkable fallback: `http://localhost:8080/webapps/clinreport` + path field (exists).

## Acceptance

A clinician on the Variant tab can open the review window without switching tabs.
