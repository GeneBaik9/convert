# patchport v2 — File Similarity Mapping Design Spec

**Date**: 2026-05-07  
**Status**: Approved  
**Author**: Gene Baik  
**Builds on**: `2026-05-07-patchport-design.md` (v1.0)

---

## Overview

patchport v1 assumed upstream and target share identical directory structures and filenames. In practice, environments differ: directory layouts diverge, filenames are slightly renamed, and OS-specific middleware layers exist only on one side.

v2 introduces a **file similarity mapping** phase that runs before the merge. It computes a confidence score for each upstream↔target file pair, presents a confirmation table, and saves the approved mapping to `.patchport-map.json`. Subsequent runs reuse the saved map automatically.

**New CLI flags:**

```bash
patchport --upstream <path> --target <path>   # uses saved map if available
patchport --upstream <path> --target <path> --remap   # forces re-mapping
```

---

## Problem Statement

When upstream and target share no common repository history **and** their directory structures diverge due to environment differences (OS, deployment target, library availability), direct path-based patching fails silently — the diff is generated correctly but applied to the wrong file or not at all.

The root causes:
- **Path drift**: `src/audio/encoder.py` → `lib/audio/encoder_v2.py`
- **Name drift**: filenames change slightly across environments
- **OS-specific middleware**: upstream has `platform/win32/driver.py`; target has a Linux-specific abstraction layer with no direct counterpart
- **Removed code**: files exist in upstream's git history but have been deliberately removed from the target environment

---

## Architecture

### New and modified files

```
patchport/
├── mapper.py       ← NEW: similarity engine + map persistence
├── cli.py          ← MODIFIED: mapping phase, --remap flag
├── patcher.py      ← MODIFIED: accepts path_map for path translation
├── reporter.py     ← MODIFIED: print_mapping_table()
└── exceptions.py   ← MODIFIED: MappingFileError
```

### Component responsibilities

| Module | Responsibility |
|---|---|
| `mapper.py` | Compute filename + content similarity scores; build candidate list; save/load `.patchport-map.json`; backup on `--remap` |
| `cli.py` | Detect whether map exists; run mapping phase or load map; pass resolved `path_map` to `apply_changes()` |
| `patcher.py` | Translate upstream file path → target file path via `path_map` before applying `git merge-file`; handle binary overwrite |
| `reporter.py` | Render mapping confirmation table with confidence scores; show binary/skip/overwrite annotations |
| `exceptions.py` | `MappingFileError` for corrupt/unreadable `.patchport-map.json` |

---

## User Workflow

### First run (no `.patchport-map.json`)

```
$ patchport --upstream ./other-repo --target ./my-code

[commit selection — same as v1]

Analyzing file similarity (23 files)...

┌──────────────────────────────────────────────────────────────────────────┐
│  File Mapping Candidates                                                 │
├───┬────────────────────────────┬───────────────────────────┬────────────┤
│ # │ Upstream file              │ Your file (suggested)     │ Confidence │
├───┼────────────────────────────┼───────────────────────────┼────────────┤
│ 1 │ src/audio/encoder.py       │ lib/audio/encoder_v2.py   │  94%       │
│ 2 │ src/config.py              │ config/config_mgr.py      │  88%       │
│ 3 │ src/codec/h264.py          │ codec/h264_linux.py       │  81%       │
│ 4 │ assets/logo.png            │ assets/logo.png           │ [binary — overwrite] │
│ 5 │ src/win32/driver.py        │ (unmapped — skip)         │  11%       │
└───┴────────────────────────────┴───────────────────────────┴────────────┘

Edit a mapping? Enter row number to change, or press Enter to confirm all:
> 5

Row 5 — src/win32/driver.py
  Current: (unmapped — skip)
  Enter target path (or 'skip' to keep skipping, 'overwrite' for binary):
> skip

Mapping saved to .patchport-map.json
Applying diff...
```

### Subsequent runs (map exists)

```
$ patchport --upstream ./other-repo --target ./my-code

[commit selection]

✔ Loaded mapping from .patchport-map.json (23 entries)
Applying diff...
```

### Force re-map

```
$ patchport --upstream ./other-repo --target ./my-code --remap

Existing map backed up to .patchport-map.json.bak
Analyzing file similarity...
[mapping confirmation table shown again]
```

### New upstream file not in saved map

When a new file appears in upstream that has no entry in `.patchport-map.json`:

```
⚠  1 new upstream file not in saved map — running similarity check...

┌───┬──────────────────────────┬───────────────────────────┬────────────┐
│ # │ Upstream file            │ Your file (suggested)     │ Confidence │
├───┼──────────────────────────┼───────────────────────────┼────────────┤
│ 1 │ src/subtitle/new.py      │ lib/subtitle/subtitle.py  │  76%       │
└───┴──────────────────────────┴───────────────────────────┴────────────┘

Confirm and update map? [Enter / edit row number]:
```

---

## Similarity Algorithm

**Pure Python — no external dependencies.**

```python
from difflib import SequenceMatcher
from pathlib import Path

FILENAME_WEIGHT = 0.3
CONTENT_WEIGHT  = 0.7
MATCH_THRESHOLD = 0.5   # score below this → unmapped


def compute_score(
    upstream_path: str, upstream_content: str,
    target_path: str,   target_content: str,
) -> float:
    name_score = SequenceMatcher(
        None,
        Path(upstream_path).name,
        Path(target_path).name,
    ).ratio()

    content_score = SequenceMatcher(
        None, upstream_content, target_content
    ).ratio()

    return FILENAME_WEIGHT * name_score + CONTENT_WEIGHT * content_score
```

**Candidate selection**: For each upstream file, compute scores against all target files. Return the target file with the highest score. If highest score < `MATCH_THRESHOLD` → unmapped.

**Performance**: SequenceMatcher on 50 files × 50 files = 2,500 comparisons. At typical file sizes (< 500 lines), this completes in under 2 seconds.

---

## Binary File Handling

A file is detected as binary if it contains a null byte (`\x00`) in its first 8,192 bytes.

**Default behavior**: overwrite target file with upstream's latest version.

**In the mapping table**: binary files display `[binary — overwrite]` in the Confidence column.

**User override during confirmation**: enter the row number and type `skip` to prevent overwrite.

**In `.patchport-map.json`**: binary files saved as:
```json
"assets/logo.png": {"target": "assets/logo.png", "binary": true, "action": "overwrite"}
```
`"action"` can be `"overwrite"` or `"skip"`.

---

## `.patchport-map.json` Format

Saved in the `--target` directory root.

```json
{
  "version": "2",
  "created": "2026-05-07",
  "upstream": "/path/to/other-repo",
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

- String value → target file path (text merge)
- `null` → explicitly skipped (no merge, no overwrite)
- Object with `"binary": true` → binary file with explicit action

**Backup on `--remap`**: existing file renamed to `.patchport-map.json.bak` before overwrite.

---

## Error Handling

| Condition | Behavior |
|---|---|
| `.patchport-map.json` is corrupt / invalid JSON | Exit with `MappingFileError`; suggest `--remap` |
| User-entered target path does not exist | Prompt again with error message |
| All upstream files are unmapped | Warn user and exit cleanly (nothing to merge) |
| Binary file — `action: overwrite` — target doesn't exist | Create the file (same as new file) |
| `--remap` — `.patchport-map.json.bak` already exists | Overwrite `.bak` silently |

---

## CLI Reference (updated)

```
Usage: patchport [OPTIONS]

Options:
  --upstream PATH    Path to the upstream Git repository (with history).
                     [required]
  --target PATH      Path to your local codebase directory to patch.
                     [required]
  --limit INTEGER    Number of recent commits to display.  [default: 20]
  --dry-run          Show which files would change without modifying anything.
  --remap            Ignore saved mapping and rebuild from scratch.
                     Backs up existing .patchport-map.json to .patchport-map.json.bak.
  --version          Show version and exit.
  -h, --help         Show this message and exit.
```

---

## New Module: mapper.py

```python
# Public interface

@dataclass
class MappingCandidate:
    upstream_path: str
    target_path: str | None    # None = unmapped
    score: float
    is_binary: bool
    action: str                # "merge" | "overwrite" | "skip"


def build_candidates(
    upstream_files: dict[str, str],   # path → content
    target_files: dict[str, str],     # path → content
) -> list[MappingCandidate]: ...


def load_map(target_dir: Path) -> dict | None: ...
def save_map(target_dir: Path, candidates: list[MappingCandidate]) -> None: ...
def backup_map(target_dir: Path) -> None: ...
def is_binary(content: bytes) -> bool: ...
```

---

## Modified: patcher.py

`apply_changes()` signature changes:

```python
# v1
def apply_changes(upstream, target, from_hash, to_hash) -> list[FileResult]: ...

# v2
def apply_changes(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    candidates: list[MappingCandidate],  # resolved mapping from mapper.py
) -> list[FileResult]: ...
```

`_merge_file()` looks up the `MappingCandidate` for each upstream file path. If `candidate.action == "skip"` → return `FileResult(status="skipped")`. If `candidate.action == "overwrite"` (binary) → write upstream content directly. If `candidate.action == "merge"` → run `git merge-file` on `candidate.target_path`.

---

## Testing Strategy

| Layer | What to test |
|---|---|
| Unit — `mapper.py` — `compute_score` | Same content = 1.0; empty vs full = low score; filename weight applied correctly |
| Unit — `mapper.py` — `build_candidates` | Best match selected; unmapped when score < threshold; binary detection |
| Unit — `mapper.py` — `save_map` / `load_map` | Round-trip JSON serialization; backup on remap |
| Unit — `patcher.py` — path translation | Path in `path_map` used instead of original path; `null` entry → skipped; binary → overwritten |
| Integration — full flow | Two repos with different directory structure; run patchport; assert correct target file patched |
| Integration — `--remap` | Run twice; second run with `--remap`; assert `.bak` created and new map differs |

---

## Security Considerations (additions to v1)

- `.patchport-map.json` is read with `json.loads()` — no `eval()` or dynamic execution
- User-supplied target paths (edited during confirmation) are validated to exist within `--target` directory before saving — prevents path traversal
- Binary detection reads only first 8,192 bytes of each file — no unbounded memory usage

---

## Out of Scope (v2.0)

- Automatic detection of OS-specific file pairs (e.g., win32 ↔ linux counterparts) — v2.1
- Multiple upstream → single target fan-in merges
- Map file versioning / migration between patchport versions
