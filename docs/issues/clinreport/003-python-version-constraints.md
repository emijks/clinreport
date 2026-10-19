# 003 · OpenCRAVAT 2.x needs Python < 3.12 and setuptools < 81; nothing checks it

| Status | Priority | Type | Area |
|---|---|---|---|
| open | **P1** | compatibility / distribution | `install_extension.py`, README, clinician machines |

## Problem

Verified on this machine ([03 version matrix](../../reference/opencravat-integration.md#version-matrix)):

- OC **2.2.x** imports `imp` → does not run on Python ≥ 3.12.
- OC 2.2.x imports `pkg_resources` → breaks with `setuptools` ≥ 81.
- OC **2.17** runs on 3.14, but the **viewer hangs** (`nest_asyncio`), so it is unusable there.
- OC **3.x** GUI does not start on Windows.

The extension itself is 3.8+-compatible, but `install_extension.py` happily installs into any Python, and a clinician on a fresh
machine with the default Python (3.13/3.14 today) gets a broken OpenCRAVAT regardless of this extension.

**Unknown:** which OpenCRAVAT and Python versions the clinicians actually run. The example results say OC 2.2.9.

## TODO

- [ ] Ask/collect: OC version (`oc version`), Python version, OS of each clinician machine.
- [ ] `install_extension.py`: print OC + Python versions; warn if OC < 2.3 and Python ≥ 3.12, if setuptools ≥ 81 with OC 2.2.x,
      if OC ≥ 3 on Windows, if `hg38` or `wgnote` modules are missing (`au.get_local_module_info(name) is None`).
- [ ] Clinician install guide (Russian, short): Python 3.11, `pip install "open-cravat==2.2.9" "setuptools<81"`,
      `oc module install-base`, `install_extension.py`.
- [ ] Decide whether to move clinicians to OC 2.17 on Python 3.11 (untested combination — test first) — also affects [019](019-note-column-base-note-variant.md).

## Acceptance

`install_extension.py` refuses or clearly warns on known-broken combinations; a written install guide exists for clinicians.
