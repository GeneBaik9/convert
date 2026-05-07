# patchport

> Apply upstream Git changes to your local codebase — without sharing a repository.

[![PyPI version](https://badge.fury.io/py/patchport.svg)](https://pypi.org/project/patchport/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Problem

You and a collaborator maintain the same project in **separate, unlinked Git repositories** — perhaps because your environments, directory structures, or deployment targets differ too much to share a single remote.

Every time the upstream changes, you manually sift through their commits, re-apply relevant changes by hand, and hope nothing conflicts with your local customizations. This is exactly as tedious as it sounds.

## The Solution

`patchport` automates this in three steps:

1. Point it at the upstream repo and your local directory.
2. Choose which upstream commits to incorporate.
3. It builds a **file similarity map**, applies the diff via **3-way merge**, and inserts standard Git conflict markers where local and upstream diverge.

The mapping is saved to `.patchport-map.json` and reused on every subsequent run — you only review it once.

---

## Installation

```bash
pip install patchport
```

**Requirements:** Python 3.10+ and Git 2.x (installed and on your `PATH`).

---

## Quick Start

```bash
patchport --upstream /path/to/upstream-repo --target /path/to/my-code
```

---

## How It Works

### Step 1 — Select commits

patchport displays the upstream commit history and prompts you to select a range:

```
╭────────────────────────────────────────────────────────────╮
│ Commits in upstream                                        │
├────┬─────────┬──────────────────────────────┬─────────────┤
│  # │ Hash    │ Message                      │ Date        │
├────┼─────────┼──────────────────────────────┼─────────────┤
│  1 │ a1b2c3d │ Fix audio sync issue         │ 2026-05-06  │
│  2 │ e4f5g6h │ Add subtitle support         │ 2026-05-04  │
│  3 │ i7j8k9l │ Refactor encoder logic       │ 2026-05-01  │
╰────┴─────────┴──────────────────────────────┴─────────────╯

From commit [#]: 3
To commit   [#]: 1
```

### Step 2 — Confirm the file mapping

Because upstream and your local directory may have **different structures** or slightly different filenames, patchport opens a browser-based visual editor:

- **Left panel:** upstream changed files
- **Right panel:** your target files
- **Auto-suggested connections** based on filename + content similarity (30% / 70% weighting)
- **Draw lines** by dragging or clicking to connect upstream ↔ target file pairs
- **Delete a connection** by clicking the line
- Click **Confirm** when done

The confirmed mapping is saved to `.patchport-map.json` and reused automatically on future runs.

### Step 3 — Merge

```
Applying diff (4 files changed)...

  ✔  src/audio/encoder.py   patched cleanly
  ✔  src/config.py          patched cleanly
  ✔  assets/logo.png        patched cleanly
  ⚠  src/codec/h264.py      2 conflict(s) — resolve markers and re-run

────────────────────────────────────────────────────────────
  3 file(s) patched  ·  1 conflict(s) found

⚠  Resolve conflict markers above, then commit your changes.
```

Files with conflicts receive standard Git conflict markers:

```python
<<<<<<< local
feature = 'my_local_override'
||||||| upstream (base)
feature = None
=======
feature = True
>>>>>>> upstream (new)
```

Resolve them in your editor, then commit.

---

## Saved Mapping: `.patchport-map.json`

After you confirm the mapping, patchport saves it to `.patchport-map.json` in your target directory:

```json
{
  "version": "2",
  "created": "2026-05-07",
  "mappings": {
    "src/audio/encoder.py": "lib/audio/encoder_v2.py",
    "src/config.py": "config/config_mgr.py",
    "src/win32/driver.py": null,
    "assets/logo.png": {
      "target": "assets/logo.png",
      "binary": true,
      "action": "overwrite"
    }
  }
}
```

| Value type | Meaning |
|---|---|
| String | Target file path — merged via 3-way merge |
| `null` | Explicitly skipped — no merge, no overwrite |
| Object with `"binary": true` | Binary file — overwrite target with upstream version |

Subsequent runs load this file automatically. If upstream adds a new file not yet in the map, patchport opens the browser only for that file.

---

## CLI Reference

```
Usage: patchport [OPTIONS]

  Apply upstream Git changes to your local codebase — without sharing a
  repository.

Options:
  --upstream PATH    Path to the upstream Git repository (with history).
                     [required]
  --target PATH      Path to your local codebase directory to patch.
                     [required]
  --limit INTEGER    Number of recent commits to display.  [default: 20]
  --dry-run          Show what would change without modifying anything.
                     Does not open the browser or save the mapping file.
  --remap            Ignore saved mapping and rebuild from scratch.
                     Backs up existing .patchport-map.json to
                     .patchport-map.json.bak before overwriting.
  --version          Show version and exit.
  -h, --help         Show this message and exit.
```

---

## How the Similarity Score Works

For each file changed in upstream, patchport computes a score against every file in your target directory:

| Component | Weight | Description |
|---|---|---|
| Filename similarity | 30% | `difflib.SequenceMatcher` on the basename only (ignores path) |
| Content similarity | 70% | `difflib.SequenceMatcher` on the full file text |

Files scoring below the match threshold are shown as **unmapped** and skipped by default. Binary files (containing null bytes) skip content comparison and default to overwrite.

No external libraries required — patchport uses Python's built-in `difflib` module.

---

## How the 3-Way Merge Works

For each mapped text file, patchport runs `git merge-file --diff3`:

| Input | Source |
|---|---|
| **base** | Upstream file at the "from" commit |
| **other** | Upstream file at the "to" commit |
| **current** | Your local file |

`git merge-file` applies the upstream change (base → other) to your local file. If your local version hasn't diverged from the base, the change applies cleanly. If it has, conflict markers are inserted.

The upstream directory is **never modified**. Only your `--target` directory is written to.

---

## Security

- All Git commands use `subprocess` with explicit argument lists — no `shell=True`.
- User-supplied target paths are validated to exist within `--target` before saving.
- No credentials, tokens, or `.env` files are read or written.
- No network access — patchport operates entirely on the local filesystem.
- `.patchport-map.json` is parsed with `json.loads()` — no `eval()`.
- Binary detection reads only the first 8,192 bytes of each file — no unbounded memory usage.

---

## Contributing

```bash
git clone https://github.com/GeneBaik9/convert.git
cd convert
pip install -e .
pip install pytest
pytest
```

Pull requests welcome. Please include tests for any new behaviour.

---

## License

MIT © Gene Baik
