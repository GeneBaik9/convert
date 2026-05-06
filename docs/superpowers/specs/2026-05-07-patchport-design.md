# patchport — Design Spec

**Date**: 2026-05-07  
**Status**: Approved  
**Author**: Gene Baik

---

## Overview

`patchport` is a command-line tool that extracts a diff between two commits in an upstream Git repository and applies it to a separate local codebase — without requiring a shared Git history between the two.

**Target user**: A developer maintaining environment-specific modifications on top of an upstream codebase in a completely separate directory or repository. The upstream changes periodically and the developer needs to selectively incorporate those changes without overwriting their own customizations.

**Install**:
```bash
pip install patchport
```

**One-liner description**:
> Apply upstream Git changes to your local codebase — without sharing a repository.

---

## Problem Statement

When two developers work on the same project in isolated environments (different machines, different directory structures, different Git remotes), merging upstream changes is a recurring manual chore:

1. Inspect what changed upstream
2. Manually re-apply those changes locally
3. Resolve conflicts with local customizations

`patchport` automates steps 1–3 with a reproducible, auditable workflow.

---

## Architecture

```
patchport/
├── __init__.py
├── cli.py          # Click entry point — argument parsing, commit selection UI
├── git.py          # Git operations: list commits, generate unified diff
├── patcher.py      # Patch application via git apply, conflict detection
├── reporter.py     # Rich-based terminal output: tables, color, summary
└── exceptions.py   # Domain-specific exceptions
```

### Component Responsibilities

| Module | Responsibility |
|---|---|
| `cli.py` | Parse `--upstream` / `--target` flags; render commit table; prompt user for from/to selection |
| `git.py` | Run `git log` to list commits; run `git diff --name-only` to enumerate changed files; run `git show FROM:file` and `git show TO:file` to extract file versions |
| `patcher.py` | For each changed file, run `git merge-file` for 3-way merge; detect and count conflict markers; report per-file result |
| `reporter.py` | Print success/conflict summary with `rich`; list affected files with status icons |
| `exceptions.py` | `NotAGitRepoError`, `InvalidCommitRangeError`, `PatchApplicationError` |

---

## User Workflow

### Basic usage

```bash
patchport --upstream /path/to/other-repo --target /path/to/my-code
```

### Step-by-step flow

**1. Commit discovery**

`patchport` reads the upstream Git log and displays the 20 most recent commits in a numbered table:

```
┌─────────────────────────────────────────────────────────┐
│  Commits in upstream (latest 20)                        │
├───┬──────────┬───────────────────────────┬──────────────┤
│ # │ Hash     │ Message                   │ Date         │
├───┼──────────┼───────────────────────────┼──────────────┤
│ 1 │ a1b2c3d  │ Fix audio sync issue      │ 2026-05-06   │
│ 2 │ e4f5g6h  │ Add subtitle support      │ 2026-05-04   │
│ 3 │ i7j8k9l  │ Refactor encoder logic    │ 2026-05-01   │
└───┴──────────┴───────────────────────────┴──────────────┘
```

**2. Range selection**

```
From commit [#]: 3
To commit   [#]: 1
```

The diff covers all changes introduced between commit #3 (exclusive) and commit #1 (inclusive), i.e., `git diff i7j8k9l..a1b2c3d`.

**3. Patch application (per-file 3-way merge)**

For each file changed in the upstream diff, `patchport` performs a 3-way merge using `git merge-file`. This works even when the target directory is not a Git repository:

```bash
# For each changed file:
git show FROM:path/to/file  >  /tmp/old_file   # upstream at FROM
git show TO:path/to/file    >  /tmp/new_file   # upstream at TO
# target/path/to/file       =  local version

git merge-file target/path/to/file /tmp/old_file /tmp/new_file
```

`git merge-file` writes conflict markers directly into the target file when the local version and upstream's new version both diverge from the common base. No `.rej` files — standard Git conflict syntax only.

**4. Result report**

```
Applying diff (3 files changed)...

  ✔  encoder.py     patched cleanly
  ✔  subtitle.py    patched cleanly
  ⚠  config.py      2 conflict(s) — resolve markers and re-run

────────────────────────────────────────
  2 files patched  ·  1 conflict(s) found
```

Files with conflicts contain standard Git conflict markers:

```
<<<<<<< upstream (new)
new_setting = True
||||||| upstream (base)
new_setting = None
=======
new_setting = False   # my environment override
>>>>>>> local
```

The user resolves these manually, then re-runs `patchport` or commits their resolution.

---

## CLI Reference

```
Usage: patchport [OPTIONS]

  Apply upstream Git changes to a separate local codebase.

Options:
  --upstream PATH   Path to the upstream Git repository (with history).
                    [required]
  --target PATH     Path to your local codebase directory to patch.
                    [required]
  --limit INTEGER   Number of commits to display for selection. [default: 20]
  --dry-run         Show the diff without applying it.
  --version         Show version and exit.
  -h, --help        Show this message and exit.
```

---

## Data Flow

```
[upstream git repo]
       │
       ├── git log --limit N
       │         └──▶ commit list displayed to user
       │
       ├── user selects FROM..TO
       │
       └── git diff --name-only FROM..TO
                   │
                   ▼
           [list of changed files]
                   │
                   ▼ (per file)
       ┌───────────────────────────────┐
       │  git show FROM:file  → /tmp/old  │
       │  git show TO:file    → /tmp/new  │
       │  target/file         → local     │
       │                                  │
       │  git merge-file local old new    │
       └───────────────────────────────┘
                   │
           ┌───────┴────────┐
           ▼                ▼
      clean merge     conflict markers
      ✔ reported       inserted in file
                        ⚠ reported
```

---

## Error Handling

| Condition | Behavior |
|---|---|
| `--upstream` is not a Git repository | Exit with `NotAGitRepoError`; clear message |
| FROM commit number ≥ TO commit number | Exit with `InvalidCommitRangeError` |
| `--target` directory does not exist | Exit immediately with path error |
| `git merge-file` exits with code ≥ 2 (unexpected error) | Exit with `PatchApplicationError`; show stderr |
| `git show FROM:file` fails (file not in upstream at that commit) | Skip file; warn user that the file is new (added, not modified) |
| Partial conflict (some files conflict) | Continue; insert markers; report which files have conflicts |
| Empty diff (no changes in range) | Inform user: "No changes between selected commits" |

All errors are printed in red via `rich`. No tracebacks shown to end users (use `--debug` flag to expose them).

---

## Security Considerations

Since `patchport` is a public tool, the following constraints apply to the implementation:

- **No `shell=True`** in any `subprocess` call. All Git commands are passed as argument lists to prevent command injection via user-supplied paths.
- **Path validation**: `--upstream` and `--target` are resolved to absolute paths and validated before any Git command runs.
- **No credentials**: The tool never reads, writes, or transmits authentication tokens, SSH keys, or `.env` files.
- **Temp file isolation**: The patch temp file is written to `tempfile.mkstemp()` and always deleted in a `finally` block.
- **No network access**: `patchport` operates entirely on local filesystem paths. No remote Git operations (`fetch`, `pull`, `push`) are performed.
- **Read-only on upstream**: Only `git log` and `git diff` are executed against the upstream repo. The upstream directory is never modified.

---

## Package Distribution

**PyPI package name**: `patchport`  
**CLI entry point**: `patchport`  
**Python version support**: 3.9+  
**System requirement**: Git 2.x installed

### `pyproject.toml` structure

```toml
[project]
name = "patchport"
version = "0.1.0"
description = "Apply upstream Git changes to your local codebase — without sharing a repository."
requires-python = ">=3.9"
dependencies = [
    "click>=8.0",
    "rich>=13.0",
]

[project.scripts]
patchport = "patchport.cli:main"
```

---

## Testing Strategy

| Layer | What to test |
|---|---|
| Unit — `git.py` | Mock `subprocess` calls; verify correct `git log` / `git diff` arguments are constructed |
| Unit — `patcher.py` | Provide known old/new/local file content; assert `git merge-file` result matches expected output (clean or with markers) |
| Unit — `reporter.py` | Assert conflict count and file status are reported correctly |
| Integration | Create two real Git repos in `tmp`; commit changes to upstream; run `patchport`; assert target files match expected output |
| Conflict case | Create conflicting change in target before patching; assert conflict markers appear in output file |

Test framework: `pytest`. No mocking of the filesystem — use `tmp_path` fixtures.

---

## Out of Scope (v1.0)

- GUI or web interface
- Automatic conflict resolution via AI
- Support for non-Git version control systems (SVN, Mercurial)
- Remote upstream paths (`git+ssh://`, `https://`)
- Storing "last synced commit" state between runs (planned for v1.1)
