# patchport

> Apply upstream Git changes to your local codebase — without sharing a repository.

[![PyPI version](https://badge.fury.io/py/patchport.svg)](https://pypi.org/project/patchport/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Problem

You and a collaborator maintain the same project in **separate, unlinked Git repositories** — perhaps because your environments, directory structures, or deployment targets differ too much to share a single remote.

Every time the upstream changes, you manually sift through their commits, re-apply relevant changes by hand, and pray nothing conflicts with your local customizations. This is exactly as tedious as it sounds.

## The Solution

`patchport` automates this in three steps:

1. Point it at the upstream repo and your local directory.
2. Choose which upstream commits to incorporate.
3. It applies the diff using a per-file **3-way merge** — your local changes are preserved wherever possible, and standard Git conflict markers appear where they aren't.

---

## Installation

```bash
pip install patchport
```

**Requirements:** Python 3.9+ and Git 2.x (installed and on your `PATH`).

---

## Quick Start

```bash
patchport --upstream /path/to/upstream-repo --target /path/to/my-code
```

`patchport` displays the upstream commit history, prompts you to select a range, then applies the diff:

```
╭──────────────────────────────────────────────────────────╮
│ Commits in upstream                                      │
├────┬─────────┬────────────────────────────┬──────────────┤
│  # │ Hash    │ Message                    │ Date         │
├────┼─────────┼────────────────────────────┼──────────────┤
│  1 │ a1b2c3d │ Fix audio sync issue       │ 2026-05-06   │
│  2 │ e4f5g6h │ Add subtitle support       │ 2026-05-04   │
│  3 │ i7j8k9l │ Refactor encoder logic     │ 2026-05-01   │
╰────┴─────────┴────────────────────────────┴──────────────╯

From commit [#]: 3
To commit   [#]: 1

Applying diff (3 files changed)...

  ✔  encoder.py     patched cleanly
  ✔  subtitle.py    patched cleanly
  ⚠  config.py      2 conflict(s) — resolve markers and re-run

────────────────────────────────────────────────────────────
  2 file(s) patched  ·  1 conflict(s) found

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
  --dry-run          Show which files would change without modifying anything.
  --version          Show version and exit.
  -h, --help         Show this message and exit.
```

---

## How It Works

For each file changed between the selected commits, `patchport` performs a
**3-way merge** using `git merge-file`:

| Input | Source |
|---|---|
| **base** | File content at the "from" commit in upstream |
| **other** | File content at the "to" commit in upstream |
| **current** | Your local file |

`git merge-file` applies upstream's change (base → other) to your local file.
If your local version has diverged from the base, conflict markers are inserted.
If it hasn't, the change is applied cleanly.

The upstream directory is **never modified**. Only your `--target` directory is written to.

---

## Security

- All Git commands use `subprocess` with explicit argument lists — no `shell=True`, no command injection risk.
- `--upstream` and `--target` paths are resolved to absolute paths before any operation.
- No credentials, tokens, or `.env` files are read or written.
- No network access — `patchport` operates entirely on the local filesystem.

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
