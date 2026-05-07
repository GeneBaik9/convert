# patchport v2 — File Similarity Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file similarity mapping to patchport so it can merge upstream changes even when upstream and target have different directory structures and slightly different filenames.

**Architecture:** New `mapper.py` module handles similarity scoring (filename 30% + content 70%), candidate selection, and `.patchport-map.json` persistence. `patcher.py` is updated to translate upstream paths via `MappingCandidate` objects before merging. `cli.py` gains a mapping phase (build → show table → user confirms/edits → save) and a `--remap` flag. All existing v1 tests continue to pass.

**Tech Stack:** Python 3.10+, difflib.SequenceMatcher (stdlib), Click 8, Rich 13, pytest, git 2.x

---

## File Map

| File | Change |
|---|---|
| `patchport/mapper.py` | **CREATE** — MappingCandidate, is_binary, compute_score, build_candidates, save_map, load_map, backup_map |
| `patchport/exceptions.py` | **MODIFY** — add MappingFileError |
| `patchport/git.py` | **MODIFY** — add show_file_bytes_at_commit() |
| `patchport/patcher.py` | **MODIFY** — apply_changes() takes candidates; _merge_file() uses MappingCandidate |
| `patchport/reporter.py` | **MODIFY** — add print_mapping_table() |
| `patchport/cli.py` | **MODIFY** — mapping phase, --remap flag, _run_mapping_phase(), _edit_mapping_interactive() |
| `tests/test_mapper.py` | **CREATE** — unit tests for all mapper functions |
| `tests/test_git.py` | **MODIFY** — add test for show_file_bytes_at_commit |
| `tests/test_patcher.py` | **MODIFY** — update apply_changes() calls to pass candidates |
| `tests/test_reporter.py` | **MODIFY** — add test for print_mapping_table |
| `tests/test_cli_v2.py` | **CREATE** — integration tests with different directory structures |
| `README.md` | **MODIFY** — document mapping workflow, .patchport-map.json, --remap |

---

## Task 1: MappingFileError + MappingCandidate dataclass

**Files:**
- Modify: `patchport/exceptions.py`
- Create: `patchport/mapper.py`
- Create: `tests/test_mapper.py`

- [ ] **Step 1: Add MappingFileError to `patchport/exceptions.py`**

Append to the existing file (keep all existing classes):

```python


class MappingFileError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Cannot read .patchport-map.json: {detail}. "
            "Run with --remap to rebuild the mapping."
        )
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_mapper.py
from patchport.mapper import MappingCandidate


def test_mapping_candidate_defaults():
    c = MappingCandidate(
        upstream_path="src/foo.py",
        target_path="lib/foo_v2.py",
        score=0.85,
        is_binary=False,
        action="merge",
    )
    assert c.upstream_path == "src/foo.py"
    assert c.target_path == "lib/foo_v2.py"
    assert c.score == 0.85
    assert c.is_binary is False
    assert c.action == "merge"


def test_mapping_candidate_unmapped():
    c = MappingCandidate(
        upstream_path="src/win32.py",
        target_path=None,
        score=0.1,
        is_binary=False,
        action="skip",
    )
    assert c.target_path is None
    assert c.action == "skip"
```

- [ ] **Step 3: Run test — verify it fails**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v 2>&1 | head -10
```

Expected: `ImportError` (mapper.py doesn't exist)

- [ ] **Step 4: Create `patchport/mapper.py` with MappingCandidate only**

```python
from dataclasses import dataclass


@dataclass
class MappingCandidate:
    upstream_path: str
    target_path: str | None     # None = unmapped/skip
    score: float                # 0.0 to 1.0
    is_binary: bool
    action: str                 # "merge" | "overwrite" | "skip"
```

- [ ] **Step 5: Run test — verify it passes**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add patchport/mapper.py patchport/exceptions.py tests/test_mapper.py
git commit -m "feat: add MappingCandidate dataclass and MappingFileError"
```

---

## Task 2: is_binary + compute_score

**Files:**
- Modify: `patchport/mapper.py`
- Modify: `tests/test_mapper.py`

- [ ] **Step 1: Append failing tests to `tests/test_mapper.py`**

```python
from patchport.mapper import MappingCandidate, is_binary, compute_score


def test_is_binary_with_null_byte():
    assert is_binary(b"hello\x00world") is True


def test_is_binary_text_content():
    assert is_binary(b"def foo():\n    return 1\n") is False


def test_is_binary_checks_only_first_8192_bytes():
    # Long text with null byte past 8192
    data = b"x" * 8192 + b"\x00"
    assert is_binary(data) is False


def test_compute_score_identical_files():
    score = compute_score("src/foo.py", b"x = 1\n", "lib/foo.py", b"x = 1\n")
    assert score > 0.9


def test_compute_score_different_files():
    score = compute_score("src/foo.py", b"x = 1\n", "lib/bar.py", b"y = 999\nz = 'hello'\n")
    assert score < 0.5


def test_compute_score_filename_contributes():
    # Same content, very different names vs similar names
    content = b"def process(): pass\n"
    score_similar_name = compute_score("encoder.py", content, "encoder_v2.py", content)
    score_diff_name = compute_score("encoder.py", content, "completely_unrelated.py", content)
    assert score_similar_name > score_diff_name


def test_compute_score_binary_uses_filename_only():
    # Binary file — content comparison skipped, only filename contributes
    score = compute_score("logo.png", b"\x89PNG\r\n\x00", "logo.png", b"\x89PNG\r\n\x00")
    # Filename identical → name_score=1.0 → 0.3 * 1.0 = 0.3
    assert 0.25 <= score <= 0.35
```

- [ ] **Step 2: Run tests — verify new ones fail**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v 2>&1 | tail -15
```

Expected: 2 pass (existing), 7 fail (ImportError on new functions)

- [ ] **Step 3: Append to `patchport/mapper.py`**

```python
from difflib import SequenceMatcher
from pathlib import Path

FILENAME_WEIGHT = 0.3
CONTENT_WEIGHT = 0.7
MATCH_THRESHOLD = 0.5


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def compute_score(
    upstream_path: str,
    upstream_bytes: bytes,
    target_path: str,
    target_bytes: bytes,
) -> float:
    name_score = SequenceMatcher(
        None,
        Path(upstream_path).name,
        Path(target_path).name,
    ).ratio()

    if is_binary(upstream_bytes) or is_binary(target_bytes):
        return FILENAME_WEIGHT * name_score

    upstream_text = upstream_bytes.decode("utf-8", errors="replace")
    target_text = target_bytes.decode("utf-8", errors="replace")
    content_score = SequenceMatcher(None, upstream_text, target_text).ratio()

    return FILENAME_WEIGHT * name_score + CONTENT_WEIGHT * content_score
```

- [ ] **Step 4: Run all mapper tests — verify they pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/mapper.py tests/test_mapper.py
git commit -m "feat: implement is_binary and compute_score"
```

---

## Task 3: git.py — show_file_bytes_at_commit

**Files:**
- Modify: `patchport/git.py`
- Modify: `tests/test_git.py`

- [ ] **Step 1: Append failing test to `tests/test_git.py`**

```python
from patchport.git import list_commits, get_changed_files, show_file_at_commit, show_file_bytes_at_commit


def test_show_file_bytes_at_commit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    result = show_file_bytes_at_commit(upstream_repo, commits[1]["hash"], "main.py")
    assert result == b"x = 1\n"


def test_show_file_bytes_returns_none_for_missing(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    result = show_file_bytes_at_commit(upstream_repo, commits[0]["hash"], "nonexistent.py")
    assert result is None
```

- [ ] **Step 2: Run tests — verify new ones fail**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_git.py -v 2>&1 | tail -10
```

Expected: 9 pass, 2 fail (ImportError on show_file_bytes_at_commit)

- [ ] **Step 3: Append to `patchport/git.py`**

```python


def show_file_bytes_at_commit(upstream: Path, commit_hash: str, file_path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{file_path}"],
        cwd=upstream,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout
```

- [ ] **Step 4: Run all git tests — verify 11 pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_git.py -v
```

Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/git.py tests/test_git.py
git commit -m "feat: add show_file_bytes_at_commit"
```

---

## Task 4: mapper.py — build_candidates

**Files:**
- Modify: `patchport/mapper.py`
- Modify: `tests/test_mapper.py`

- [ ] **Step 1: Append failing tests to `tests/test_mapper.py`**

```python
from patchport.mapper import MappingCandidate, is_binary, compute_score, build_candidates


def test_build_candidates_finds_best_match():
    upstream_files = {"src/app.py": b"x = 1\n"}
    target_files = {
        "lib/app_v2.py": b"x = 1\n",        # nearly identical content
        "lib/unrelated.py": b"z = 999\n",
    }
    candidates = build_candidates(upstream_files, target_files)
    assert len(candidates) == 1
    assert candidates[0].upstream_path == "src/app.py"
    assert candidates[0].target_path == "lib/app_v2.py"
    assert candidates[0].action == "merge"


def test_build_candidates_unmapped_when_score_low():
    upstream_files = {"src/win32_driver.py": b"import winreg\n" * 10}
    target_files = {"lib/completely_different.py": b"import asyncio\n" * 10}
    candidates = build_candidates(upstream_files, target_files)
    assert candidates[0].target_path is None
    assert candidates[0].action == "skip"


def test_build_candidates_binary_gets_overwrite_action():
    upstream_files = {"assets/logo.png": b"\x89PNG\r\n\x00binary"}
    target_files = {"assets/logo.png": b"\x89PNG\r\n\x00old"}
    candidates = build_candidates(upstream_files, target_files)
    assert candidates[0].is_binary is True
    assert candidates[0].action == "overwrite"


def test_build_candidates_sorted_by_score_descending():
    upstream_files = {
        "src/foo.py": b"x = 1\n",
        "src/obscure.py": b"very_different = True\n" * 5,
    }
    target_files = {
        "lib/foo_v2.py": b"x = 1\n",
        "lib/other.py": b"completely_different = 42\n" * 5,
    }
    candidates = build_candidates(upstream_files, target_files)
    assert candidates[0].score >= candidates[1].score


def test_build_candidates_empty_upstream():
    candidates = build_candidates({}, {"lib/foo.py": b"x = 1\n"})
    assert candidates == []
```

- [ ] **Step 2: Run tests — verify new ones fail**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v 2>&1 | tail -15
```

Expected: 9 pass, 5 fail (ImportError on build_candidates)

- [ ] **Step 3: Append to `patchport/mapper.py`**

```python


def build_candidates(
    upstream_files: dict[str, bytes],
    target_files: dict[str, bytes],
) -> list[MappingCandidate]:
    candidates = []

    for up_path, up_bytes in upstream_files.items():
        up_is_binary = is_binary(up_bytes)
        best_score = 0.0
        best_target: str | None = None

        for tgt_path, tgt_bytes in target_files.items():
            score = compute_score(up_path, up_bytes, tgt_path, tgt_bytes)
            if score > best_score:
                best_score = score
                best_target = tgt_path

        if best_score < MATCH_THRESHOLD:
            best_target = None

        if best_target is None:
            action = "skip"
        elif up_is_binary:
            action = "overwrite"
        else:
            action = "merge"

        candidates.append(
            MappingCandidate(
                upstream_path=up_path,
                target_path=best_target,
                score=best_score,
                is_binary=up_is_binary,
                action=action,
            )
        )

    return sorted(candidates, key=lambda c: c.score, reverse=True)
```

- [ ] **Step 4: Run all mapper tests — verify 14 pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v
```

Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/mapper.py tests/test_mapper.py
git commit -m "feat: implement build_candidates"
```

---

## Task 5: mapper.py — save_map, load_map, backup_map

**Files:**
- Modify: `patchport/mapper.py`
- Modify: `tests/test_mapper.py`

- [ ] **Step 1: Append failing tests to `tests/test_mapper.py`**

```python
from patchport.mapper import (
    MappingCandidate, is_binary, compute_score, build_candidates,
    save_map, load_map, backup_map, MAP_FILENAME, MAP_BACKUP_FILENAME,
)
from patchport.exceptions import MappingFileError


def _make_candidates() -> list[MappingCandidate]:
    return [
        MappingCandidate("src/app.py", "lib/app_v2.py", 0.9, False, "merge"),
        MappingCandidate("src/win32.py", None, 0.1, False, "skip"),
        MappingCandidate("assets/logo.png", "assets/logo.png", 0.8, True, "overwrite"),
    ]


def test_save_and_load_map_roundtrip(tmp_path: Path):
    original = _make_candidates()
    save_map(tmp_path, original)
    loaded = load_map(tmp_path)
    assert loaded is not None
    assert len(loaded) == 3

    text_entry = next(c for c in loaded if c.upstream_path == "src/app.py")
    assert text_entry.target_path == "lib/app_v2.py"
    assert text_entry.action == "merge"
    assert text_entry.is_binary is False

    skip_entry = next(c for c in loaded if c.upstream_path == "src/win32.py")
    assert skip_entry.target_path is None
    assert skip_entry.action == "skip"

    binary_entry = next(c for c in loaded if c.upstream_path == "assets/logo.png")
    assert binary_entry.is_binary is True
    assert binary_entry.action == "overwrite"


def test_load_map_returns_none_when_missing(tmp_path: Path):
    assert load_map(tmp_path) is None


def test_load_map_raises_on_corrupt_json(tmp_path: Path):
    (tmp_path / MAP_FILENAME).write_text("not valid json {{{")
    import pytest
    with pytest.raises(MappingFileError):
        load_map(tmp_path)


def test_backup_map_creates_bak_file(tmp_path: Path):
    save_map(tmp_path, _make_candidates())
    backup_map(tmp_path)
    assert (tmp_path / MAP_BACKUP_FILENAME).exists()


def test_backup_map_noop_when_no_map(tmp_path: Path):
    backup_map(tmp_path)  # should not raise
    assert not (tmp_path / MAP_BACKUP_FILENAME).exists()
```

- [ ] **Step 2: Run tests — verify new ones fail**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v 2>&1 | tail -15
```

Expected: 14 pass, 5 fail

- [ ] **Step 3: Append to `patchport/mapper.py`**

```python
import json
from datetime import date

MAP_FILENAME = ".patchport-map.json"
MAP_BACKUP_FILENAME = ".patchport-map.json.bak"


def save_map(target_dir: Path, candidates: list[MappingCandidate]) -> None:
    mappings: dict = {}
    for c in candidates:
        if c.is_binary:
            mappings[c.upstream_path] = {
                "target": c.target_path,
                "binary": True,
                "action": c.action,
            }
        else:
            mappings[c.upstream_path] = c.target_path

    data = {
        "version": "2",
        "created": date.today().isoformat(),
        "mappings": mappings,
    }
    (target_dir / MAP_FILENAME).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_map(target_dir: Path) -> list[MappingCandidate] | None:
    map_file = target_dir / MAP_FILENAME
    if not map_file.exists():
        return None

    from .exceptions import MappingFileError
    try:
        data = json.loads(map_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise MappingFileError(str(e))

    candidates = []
    for upstream_path, entry in data.get("mappings", {}).items():
        if isinstance(entry, dict):
            candidates.append(MappingCandidate(
                upstream_path=upstream_path,
                target_path=entry.get("target"),
                score=1.0,
                is_binary=True,
                action=entry.get("action", "overwrite"),
            ))
        else:
            target_path = entry  # str or None
            candidates.append(MappingCandidate(
                upstream_path=upstream_path,
                target_path=target_path,
                score=1.0,
                is_binary=False,
                action="merge" if target_path is not None else "skip",
            ))
    return candidates


def backup_map(target_dir: Path) -> None:
    map_file = target_dir / MAP_FILENAME
    if map_file.exists():
        bak = target_dir / MAP_BACKUP_FILENAME
        bak.write_bytes(map_file.read_bytes())
```

- [ ] **Step 4: Run all mapper tests — verify 19 pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_mapper.py -v
```

Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/mapper.py tests/test_mapper.py
git commit -m "feat: implement save_map, load_map, backup_map"
```

---

## Task 6: reporter.py — print_mapping_table

**Files:**
- Modify: `patchport/reporter.py`
- Modify: `tests/test_reporter.py`

- [ ] **Step 1: Append failing tests to `tests/test_reporter.py`**

```python
from patchport.mapper import MappingCandidate
from patchport.reporter import print_mapping_table


def test_print_mapping_table_shows_upstream_path():
    candidates = [
        MappingCandidate("src/app.py", "lib/app_v2.py", 0.92, False, "merge"),
    ]
    output = _capture_output(print_mapping_table, candidates)
    assert "src/app.py" in output
    assert "lib/app_v2.py" in output


def test_print_mapping_table_shows_unmapped():
    candidates = [
        MappingCandidate("src/win32.py", None, 0.08, False, "skip"),
    ]
    output = _capture_output(print_mapping_table, candidates)
    assert "src/win32.py" in output
    assert "unmapped" in output.lower() or "skip" in output.lower()


def test_print_mapping_table_shows_binary():
    candidates = [
        MappingCandidate("assets/logo.png", "assets/logo.png", 0.8, True, "overwrite"),
    ]
    output = _capture_output(print_mapping_table, candidates)
    assert "logo.png" in output
    assert "binary" in output.lower() or "overwrite" in output.lower()
```

- [ ] **Step 2: Run tests — verify new ones fail**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_reporter.py -v 2>&1 | tail -10
```

Expected: 4 pass, 3 fail

- [ ] **Step 3: Append to `patchport/reporter.py`**

Add import at top of the existing file (after existing imports):

```python
from .mapper import MappingCandidate
```

Append function:

```python


def print_mapping_table(
    candidates: list[MappingCandidate], con: Console | None = None
) -> None:
    con = con or console
    table = Table(
        title="File Mapping Candidates",
        box=box.ROUNDED,
        show_lines=False,
        title_style="bold",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Upstream file", style="cyan")
    table.add_column("Your file (suggested)")
    table.add_column("Confidence", width=22, justify="right")

    for i, c in enumerate(candidates, 1):
        if c.is_binary:
            conf = "[dim][binary — overwrite][/dim]"
            target_str = c.target_path or "(unmapped — skip)"
        elif c.target_path is None:
            conf = f"[red]{c.score:.0%}[/red]"
            target_str = "[dim](unmapped — skip)[/dim]"
        elif c.score >= 0.8:
            conf = f"[green]{c.score:.0%}[/green]"
            target_str = c.target_path
        else:
            conf = f"[yellow]{c.score:.0%}[/yellow]"
            target_str = c.target_path

        table.add_row(str(i), c.upstream_path, target_str, conf)

    con.print(table)
```

- [ ] **Step 4: Run all reporter tests — verify 7 pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_reporter.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/reporter.py tests/test_reporter.py
git commit -m "feat: add print_mapping_table to reporter"
```

---

## Task 7: patcher.py — update apply_changes to use MappingCandidate

**Files:**
- Modify: `patchport/patcher.py`
- Modify: `tests/test_patcher.py`

- [ ] **Step 1: Update `tests/test_patcher.py`** — update existing tests to pass candidates

Replace the entire file content:

```python
# tests/test_patcher.py
import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits
from patchport.mapper import MappingCandidate
from patchport.patcher import apply_changes, FileResult


def _identity_candidate(file_path: str) -> MappingCandidate:
    return MappingCandidate(
        upstream_path=file_path,
        target_path=file_path,
        score=1.0,
        is_binary=False,
        action="merge",
    )


@pytest.fixture
def repos(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("version = 1\nfeature = False\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("version = 2\nfeature = True\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("version = 1\nfeature = 'my_override'\n")

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]
    to_hash = commits[0]["hash"]
    return upstream, target, from_hash, to_hash


@pytest.fixture
def clean_repos(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v1"], cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v2"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("x = 1\n")

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]
    to_hash = commits[0]["hash"]
    return upstream, target, from_hash, to_hash


def test_clean_merge_updates_file(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    candidates = [_identity_candidate("app.py")]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert len(results) == 1
    assert results[0].path == "app.py"
    assert results[0].status == "patched"
    assert (target / "app.py").read_text() == "x = 2\n"


def test_conflict_inserts_markers(repos):
    upstream, target, from_hash, to_hash = repos
    candidates = [_identity_candidate("app.py")]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert len(results) == 1
    assert results[0].status == "conflict"
    assert results[0].conflict_count >= 1
    content = (target / "app.py").read_text()
    assert "<<<<<<< " in content
    assert "=======" in content
    assert ">>>>>>> " in content


def test_new_file_is_created(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "old.py").write_text("pass\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=upstream, check=True, capture_output=True)

    (upstream / "new.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add new.py"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "old.py").write_text("pass\n")

    commits = list_commits(upstream)
    candidates = [_identity_candidate("new.py")]
    results = apply_changes(upstream, target, commits[1]["hash"], commits[0]["hash"], candidates)

    new_file_result = next(r for r in results if r.path == "new.py")
    assert new_file_result.status == "patched"
    assert (target / "new.py").read_text() == "print('hello')\n"


def test_apply_changes_returns_list_of_file_results(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    candidates = [_identity_candidate("app.py")]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert isinstance(results, list)
    assert all(isinstance(r, FileResult) for r in results)


def test_skip_action_returns_skipped(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    candidates = [
        MappingCandidate("app.py", None, 0.1, False, "skip")
    ]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert results[0].status == "skipped"


def test_path_mapping_applies_to_different_target_file(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    # upstream: app.py → target: lib/app_v2.py (renamed)
    (target / "lib").mkdir()
    (target / "lib" / "app_v2.py").write_text("x = 1\n")  # same as old upstream
    candidates = [
        MappingCandidate("app.py", "lib/app_v2.py", 0.9, False, "merge")
    ]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert results[0].status == "patched"
    assert (target / "lib" / "app_v2.py").read_text() == "x = 2\n"


def test_binary_overwrite_action(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "logo.png").write_bytes(b"\x89PNG\x00old")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "logo.png").write_bytes(b"\x89PNG\x00new")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update logo"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "logo.png").write_bytes(b"\x89PNG\x00local")

    commits = list_commits(upstream)
    candidates = [
        MappingCandidate("logo.png", "logo.png", 0.8, True, "overwrite")
    ]
    results = apply_changes(upstream, target, commits[1]["hash"], commits[0]["hash"], candidates)
    assert results[0].status == "patched"
    assert (target / "logo.png").read_bytes() == b"\x89PNG\x00new"
```

- [ ] **Step 2: Run tests — verify old tests fail (signature mismatch)**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_patcher.py -v 2>&1 | tail -15
```

Expected: failures due to `apply_changes()` missing `candidates` argument

- [ ] **Step 3: Rewrite `patchport/patcher.py`**

```python
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .exceptions import PatchApplicationError
from .git import get_changed_files, show_file_at_commit, show_file_bytes_at_commit
from .mapper import MappingCandidate


@dataclass
class FileResult:
    path: str
    status: str  # "patched" | "conflict" | "skipped"
    conflict_count: int = 0


def apply_changes(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    candidates: list[MappingCandidate],
) -> list[FileResult]:
    candidate_map = {c.upstream_path: c for c in candidates}
    changed_files = get_changed_files(upstream, from_hash, to_hash)

    results = []
    for file_path in changed_files:
        candidate = candidate_map.get(file_path)
        if candidate is None:
            results.append(FileResult(path=file_path, status="skipped"))
            continue
        results.append(_merge_file(upstream, target, from_hash, to_hash, candidate))
    return results


def _merge_file(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    candidate: MappingCandidate,
) -> FileResult:
    file_path = candidate.upstream_path

    if candidate.action == "skip":
        return FileResult(path=file_path, status="skipped")

    if candidate.action == "overwrite":
        new_bytes = show_file_bytes_at_commit(upstream, to_hash, file_path)
        if new_bytes is None:
            return FileResult(path=file_path, status="skipped")
        local_file = target / candidate.target_path
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_bytes(new_bytes)
        return FileResult(path=file_path, status="patched")

    # action == "merge"
    new_content = show_file_at_commit(upstream, to_hash, file_path)
    if new_content is None:
        return FileResult(path=file_path, status="skipped")

    local_file = target / candidate.target_path
    old_content = show_file_at_commit(upstream, from_hash, file_path)

    if old_content is None or not local_file.exists():
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_text(new_content)
        return FileResult(path=file_path, status="patched")

    with (
        tempfile.NamedTemporaryFile(mode="w", suffix=".base", delete=False) as f_old,
        tempfile.NamedTemporaryFile(mode="w", suffix=".other", delete=False) as f_new,
    ):
        f_old.write(old_content)
        old_path = f_old.name
        f_new.write(new_content)
        new_path = f_new.name

    try:
        result = subprocess.run(
            [
                "git", "merge-file",
                "--diff3",
                "-L", "local",
                "-L", "upstream (base)",
                "-L", "upstream (new)",
                str(local_file),
                old_path,
                new_path,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode < 0:
            raise PatchApplicationError(file_path, result.stderr)

        if result.returncode == 0:
            return FileResult(path=file_path, status="patched")

        content = local_file.read_text(errors="replace")
        count = content.count("<<<<<<< ")
        return FileResult(path=file_path, status="conflict", conflict_count=count)

    finally:
        for p in (old_path, new_path):
            Path(p).unlink(missing_ok=True)
```

- [ ] **Step 4: Run all patcher tests — verify 7 pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_patcher.py -v
```

Expected: 7 passed

- [ ] **Step 5: Run full suite to catch regressions**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest -v 2>&1 | tail -20
```

Expected: failures only in `tests/test_cli.py` (cli.py not yet updated — expected)

- [ ] **Step 6: Commit**

```bash
git add patchport/patcher.py tests/test_patcher.py
git commit -m "feat: update patcher to use MappingCandidate for path translation and binary overwrite"
```

---

## Task 8: cli.py — mapping phase + --remap flag

**Files:**
- Modify: `patchport/cli.py`
- Create: `tests/test_cli_v2.py`

- [ ] **Step 1: Write integration tests first at `tests/test_cli_v2.py`**

```python
# tests/test_cli_v2.py
import subprocess
from pathlib import Path
import pytest
from click.testing import CliRunner
from patchport.cli import main
from patchport.mapper import MAP_FILENAME, MAP_BACKUP_FILENAME


@pytest.fixture
def diff_structure_repos(tmp_path: Path):
    """upstream: src/app.py — target: lib/app_v2.py (different path, similar content)."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "src").mkdir()
    (upstream / "src" / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "src" / "app.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump x"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    (target / "lib").mkdir(parents=True)
    (target / "lib" / "app_v2.py").write_text("x = 1\n")  # matches old upstream content

    return upstream, target


def test_cli_v2_maps_and_patches_different_structure(diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        # commit selection: From #2 (older) To #1 (newer), then Enter to confirm mapping
        input="2\n1\n\n",
    )
    assert result.exit_code == 0, result.output
    # lib/app_v2.py should now contain x = 2 (patched via mapping)
    assert (target / "lib" / "app_v2.py").read_text() == "x = 2\n"


def test_cli_v2_saves_map_file(diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n\n",
    )
    assert (target / MAP_FILENAME).exists()


def test_cli_v2_reuses_saved_map(diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    # First run: build and save map
    runner.invoke(main, ["--upstream", str(upstream), "--target", str(target)], input="2\n1\n\n")
    # Reset target file
    (target / "lib" / "app_v2.py").write_text("x = 1\n")
    # Second run: should reuse map without mapping phase
    result = runner.invoke(main, ["--upstream", str(upstream), "--target", str(target)], input="2\n1\n")
    assert result.exit_code == 0, result.output
    assert "Loaded mapping" in result.output
    assert (target / "lib" / "app_v2.py").read_text() == "x = 2\n"


def test_cli_v2_remap_creates_backup(diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    # First run: save map
    runner.invoke(main, ["--upstream", str(upstream), "--target", str(target)], input="2\n1\n\n")
    # Reset and remap
    (target / "lib" / "app_v2.py").write_text("x = 1\n")
    runner.invoke(main, ["--upstream", str(upstream), "--target", str(target), "--remap"], input="2\n1\n\n")
    assert (target / MAP_BACKUP_FILENAME).exists()


def test_cli_v2_dry_run_does_not_save_map(diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target), "--dry-run"],
        input="2\n1\n\n",
    )
    assert not (target / MAP_FILENAME).exists()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_cli_v2.py -v 2>&1 | head -20
```

Expected: failures (cli not yet updated)

- [ ] **Step 3: Rewrite `patchport/cli.py`**

```python
import sys
from pathlib import Path

import click

from .exceptions import MappingFileError, NotAGitRepoError, PatchApplicationError
from .git import get_changed_files, list_commits, show_file_bytes_at_commit
from .mapper import (
    MappingCandidate,
    backup_map,
    build_candidates,
    load_map,
    save_map,
)
from .patcher import apply_changes
from .reporter import console, print_commit_table, print_mapping_table, print_results


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--upstream",
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
    help="Path to the upstream Git repository (with history).",
)
@click.option(
    "--target",
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
    help="Path to your local codebase directory to patch.",
)
@click.option("--limit", default=20, show_default=True, help="Number of recent commits to display.")
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying anything.")
@click.option("--remap", is_flag=True, help="Ignore saved mapping and rebuild from scratch.")
@click.version_option()
def main(upstream: Path, target: Path, limit: int, dry_run: bool, remap: bool) -> None:
    """Apply upstream Git changes to your local codebase — without sharing a repository.

    Displays recent commits from UPSTREAM, lets you select a range, builds a
    file similarity map if needed, then applies changes to TARGET via 3-way merge.
    Conflict markers are inserted where local and upstream diverge.
    """
    try:
        commits = list_commits(upstream, limit)
    except NotAGitRepoError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not commits:
        console.print("[yellow]No commits found in the upstream repository.[/yellow]")
        sys.exit(0)

    print_commit_table(commits)

    n = len(commits)
    from_idx = click.prompt("From commit [#]", type=click.IntRange(1, n))
    to_idx = click.prompt("To commit   [#]", type=click.IntRange(1, n))

    if from_idx <= to_idx:
        console.print(
            "[red]Error:[/red] 'From' must be an older commit than 'To'. "
            "Pick a higher number for 'From' (higher = older in the list above)."
        )
        sys.exit(1)

    from_hash = commits[from_idx - 1]["hash"]
    to_hash = commits[to_idx - 1]["hash"]

    changed = get_changed_files(upstream, from_hash, to_hash)
    if not changed:
        console.print("[dim]No changes between the selected commits.[/dim]")
        sys.exit(0)

    # --- Mapping phase ---
    candidates = _resolve_candidates(upstream, target, from_hash, to_hash, changed, remap, dry_run)

    if not candidates or all(c.action == "skip" for c in candidates):
        console.print("[yellow]All files are unmapped — nothing to apply.[/yellow]")
        sys.exit(0)

    console.print(f"\nApplying diff ({len(changed)} file(s) changed)...\n")

    if dry_run:
        for c in candidates:
            label = f"{c.upstream_path} → {c.target_path or '(skip)'}"
            console.print(f"  [dim]~[/dim]  {label}")
        console.print("\n[dim]Dry run — no files were modified.[/dim]")
        sys.exit(0)

    try:
        results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    except PatchApplicationError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    print_results(results)


def _resolve_candidates(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    changed_files: list[str],
    remap: bool,
    dry_run: bool,
) -> list[MappingCandidate]:
    if remap:
        backup_map(target)

    if not remap:
        try:
            saved = load_map(target)
        except MappingFileError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

        if saved is not None:
            console.print(
                f"\n[green]✔[/green] Loaded mapping from .patchport-map.json "
                f"({len(saved)} entries)"
            )
            saved_paths = {c.upstream_path for c in saved}
            new_files = [f for f in changed_files if f not in saved_paths]
            if new_files:
                console.print(
                    f"\n[yellow]⚠[/yellow]  {len(new_files)} new upstream file(s) "
                    "not in saved map — running similarity check..."
                )
                new_candidates = _build_and_confirm(upstream, target, from_hash, new_files, dry_run)
                if not dry_run:
                    save_map(target, saved + new_candidates)
                return saved + new_candidates
            return saved

    candidates = _build_and_confirm(upstream, target, from_hash, changed_files, dry_run)
    if not dry_run:
        save_map(target, candidates)
        console.print("\n[green]✔[/green] Mapping saved to .patchport-map.json")
    return candidates


def _build_and_confirm(
    upstream: Path,
    target: Path,
    from_hash: str,
    changed_files: list[str],
    dry_run: bool,
) -> list[MappingCandidate]:
    console.print(f"\nAnalyzing file similarity ({len(changed_files)} files)...\n")

    upstream_files: dict[str, bytes] = {}
    for f in changed_files:
        raw = show_file_bytes_at_commit(upstream, from_hash, f)
        if raw is None:
            from .git import show_file_bytes_at_commit as sfb
            raw = sfb(upstream, from_hash, f)
        if raw is not None:
            upstream_files[f] = raw

    target_files: dict[str, bytes] = {}
    for p in target.rglob("*"):
        if p.is_file() and p.name not in (".patchport-map.json", ".patchport-map.json.bak"):
            rel = str(p.relative_to(target))
            try:
                target_files[rel] = p.read_bytes()
            except OSError:
                pass

    candidates = build_candidates(upstream_files, target_files)
    print_mapping_table(candidates)

    if dry_run:
        return candidates

    return _edit_mapping_interactive(candidates, target)


def _edit_mapping_interactive(
    candidates: list[MappingCandidate], target: Path
) -> list[MappingCandidate]:
    while True:
        choice = click.prompt(
            "\nEdit a mapping? Enter row number to change, or press Enter to confirm all",
            default="",
            show_default=False,
        )
        if not choice.strip():
            break

        try:
            row = int(choice.strip())
        except ValueError:
            console.print("[red]Enter a row number or press Enter.[/red]")
            continue

        if not (1 <= row <= len(candidates)):
            console.print(f"[red]Row must be between 1 and {len(candidates)}.[/red]")
            continue

        c = candidates[row - 1]
        console.print(f"\nRow {row} — {c.upstream_path}")
        console.print(f"  Current: {c.target_path or '(unmapped — skip)'}")

        default = "skip" if c.target_path is None else c.target_path
        new_val = click.prompt("  Enter target path (or 'skip', 'overwrite')", default=default)
        new_val = new_val.strip()

        if new_val.lower() == "skip":
            candidates[row - 1] = MappingCandidate(c.upstream_path, None, c.score, c.is_binary, "skip")
        elif new_val.lower() == "overwrite":
            candidates[row - 1] = MappingCandidate(c.upstream_path, c.target_path, c.score, True, "overwrite")
        else:
            full = target / new_val
            if not full.exists():
                console.print(f"[red]Path not found:[/red] {full}")
            else:
                action = "overwrite" if c.is_binary else "merge"
                candidates[row - 1] = MappingCandidate(c.upstream_path, new_val, c.score, c.is_binary, action)

    return candidates
```

- [ ] **Step 4: Fix the redundant import in `_build_and_confirm`**

The `show_file_bytes_at_commit` is already imported at the top. Remove the internal import:

Replace:
```python
    upstream_files: dict[str, bytes] = {}
    for f in changed_files:
        raw = show_file_bytes_at_commit(upstream, from_hash, f)
        if raw is None:
            from .git import show_file_bytes_at_commit as sfb
            raw = sfb(upstream, from_hash, f)
        if raw is not None:
            upstream_files[f] = raw
```

With:
```python
    upstream_files: dict[str, bytes] = {}
    for f in changed_files:
        raw = show_file_bytes_at_commit(upstream, from_hash, f)
        if raw is None:
            raw = show_file_bytes_at_commit(upstream, to_hash, f)
        if raw is not None:
            upstream_files[f] = raw
```

Wait — `_build_and_confirm` doesn't have `to_hash` in scope. Fix the signature:

```python
def _build_and_confirm(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,         # ← add this
    changed_files: list[str],
    dry_run: bool,
) -> list[MappingCandidate]:
```

And update all three call sites in `_resolve_candidates` to pass `to_hash`:

```python
new_candidates = _build_and_confirm(upstream, target, from_hash, to_hash, new_files, dry_run)
```

```python
candidates = _build_and_confirm(upstream, target, from_hash, to_hash, changed_files, dry_run)
```

Also update `_resolve_candidates` signature:

```python
def _resolve_candidates(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    changed_files: list[str],
    remap: bool,
    dry_run: bool,
) -> list[MappingCandidate]:
```

Write the corrected final `patchport/cli.py` (clean version with all fixes applied):

```python
import sys
from pathlib import Path

import click

from .exceptions import MappingFileError, NotAGitRepoError, PatchApplicationError
from .git import get_changed_files, list_commits, show_file_bytes_at_commit
from .mapper import (
    MappingCandidate,
    backup_map,
    build_candidates,
    load_map,
    save_map,
)
from .patcher import apply_changes
from .reporter import console, print_commit_table, print_mapping_table, print_results


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--upstream",
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
    help="Path to the upstream Git repository (with history).",
)
@click.option(
    "--target",
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
    help="Path to your local codebase directory to patch.",
)
@click.option("--limit", default=20, show_default=True, help="Number of recent commits to display.")
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying anything.")
@click.option("--remap", is_flag=True, help="Ignore saved mapping and rebuild from scratch.")
@click.version_option()
def main(upstream: Path, target: Path, limit: int, dry_run: bool, remap: bool) -> None:
    """Apply upstream Git changes to your local codebase — without sharing a repository.

    Displays recent commits from UPSTREAM, lets you select a range, builds a
    file similarity map if needed, then applies changes to TARGET via 3-way merge.
    Conflict markers are inserted where local and upstream diverge.
    """
    try:
        commits = list_commits(upstream, limit)
    except NotAGitRepoError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not commits:
        console.print("[yellow]No commits found in the upstream repository.[/yellow]")
        sys.exit(0)

    print_commit_table(commits)

    n = len(commits)
    from_idx = click.prompt("From commit [#]", type=click.IntRange(1, n))
    to_idx = click.prompt("To commit   [#]", type=click.IntRange(1, n))

    if from_idx <= to_idx:
        console.print(
            "[red]Error:[/red] 'From' must be an older commit than 'To'. "
            "Pick a higher number for 'From' (higher = older in the list above)."
        )
        sys.exit(1)

    from_hash = commits[from_idx - 1]["hash"]
    to_hash = commits[to_idx - 1]["hash"]

    changed = get_changed_files(upstream, from_hash, to_hash)
    if not changed:
        console.print("[dim]No changes between the selected commits.[/dim]")
        sys.exit(0)

    candidates = _resolve_candidates(upstream, target, from_hash, to_hash, changed, remap, dry_run)

    if not candidates or all(c.action == "skip" for c in candidates):
        console.print("[yellow]All files are unmapped — nothing to apply.[/yellow]")
        sys.exit(0)

    console.print(f"\nApplying diff ({len(changed)} file(s) changed)...\n")

    if dry_run:
        for c in candidates:
            label = f"{c.upstream_path} → {c.target_path or '(skip)'}"
            console.print(f"  [dim]~[/dim]  {label}")
        console.print("\n[dim]Dry run — no files were modified.[/dim]")
        sys.exit(0)

    try:
        results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    except PatchApplicationError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    print_results(results)


def _resolve_candidates(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    changed_files: list[str],
    remap: bool,
    dry_run: bool,
) -> list[MappingCandidate]:
    if remap:
        backup_map(target)

    if not remap:
        try:
            saved = load_map(target)
        except MappingFileError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

        if saved is not None:
            console.print(
                f"\n[green]✔[/green] Loaded mapping from .patchport-map.json "
                f"({len(saved)} entries)"
            )
            saved_paths = {c.upstream_path for c in saved}
            new_files = [f for f in changed_files if f not in saved_paths]
            if new_files:
                console.print(
                    f"\n[yellow]⚠[/yellow]  {len(new_files)} new upstream file(s) "
                    "not in saved map — running similarity check..."
                )
                new_candidates = _build_and_confirm(upstream, target, from_hash, to_hash, new_files, dry_run)
                if not dry_run:
                    save_map(target, saved + new_candidates)
                return saved + new_candidates
            return saved

    candidates = _build_and_confirm(upstream, target, from_hash, to_hash, changed_files, dry_run)
    if not dry_run:
        save_map(target, candidates)
        console.print("\n[green]✔[/green] Mapping saved to .patchport-map.json")
    return candidates


def _build_and_confirm(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    changed_files: list[str],
    dry_run: bool,
) -> list[MappingCandidate]:
    console.print(f"\nAnalyzing file similarity ({len(changed_files)} files)...\n")

    upstream_files: dict[str, bytes] = {}
    for f in changed_files:
        raw = show_file_bytes_at_commit(upstream, from_hash, f)
        if raw is None:
            raw = show_file_bytes_at_commit(upstream, to_hash, f)
        if raw is not None:
            upstream_files[f] = raw

    target_files: dict[str, bytes] = {}
    for p in target.rglob("*"):
        if p.is_file() and p.name not in (".patchport-map.json", ".patchport-map.json.bak"):
            rel = str(p.relative_to(target))
            try:
                target_files[rel] = p.read_bytes()
            except OSError:
                pass

    candidates = build_candidates(upstream_files, target_files)
    print_mapping_table(candidates)

    if dry_run:
        return candidates

    return _edit_mapping_interactive(candidates, target)


def _edit_mapping_interactive(
    candidates: list[MappingCandidate], target: Path
) -> list[MappingCandidate]:
    while True:
        choice = click.prompt(
            "\nEdit a mapping? Enter row number to change, or press Enter to confirm all",
            default="",
            show_default=False,
        )
        if not choice.strip():
            break

        try:
            row = int(choice.strip())
        except ValueError:
            console.print("[red]Enter a row number or press Enter.[/red]")
            continue

        if not (1 <= row <= len(candidates)):
            console.print(f"[red]Row must be between 1 and {len(candidates)}.[/red]")
            continue

        c = candidates[row - 1]
        console.print(f"\nRow {row} — {c.upstream_path}")
        console.print(f"  Current: {c.target_path or '(unmapped — skip)'}")

        default = "skip" if c.target_path is None else c.target_path
        new_val = click.prompt("  Enter target path (or 'skip', 'overwrite')", default=default)
        new_val = new_val.strip()

        if new_val.lower() == "skip":
            candidates[row - 1] = MappingCandidate(c.upstream_path, None, c.score, c.is_binary, "skip")
        elif new_val.lower() == "overwrite":
            candidates[row - 1] = MappingCandidate(c.upstream_path, c.target_path, c.score, True, "overwrite")
        else:
            full = target / new_val
            if not full.exists():
                console.print(f"[red]Path not found:[/red] {full}")
            else:
                action = "overwrite" if c.is_binary else "merge"
                candidates[row - 1] = MappingCandidate(c.upstream_path, new_val, c.score, c.is_binary, action)

    return candidates
```

- [ ] **Step 5: Run v2 CLI tests — verify they pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest tests/test_cli_v2.py -v
```

Expected: 5 passed

- [ ] **Step 6: Run full suite — verify all tests pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest -v
```

Expected: all tests pass (test_cli.py v1 tests may need `input="2\n1\n\n"` — if they fail due to new mapping prompt, add extra `\n` to their input)

- [ ] **Step 7: Fix test_cli.py if needed**

If v1 CLI tests fail because the mapping phase now prompts for confirmation, update `input` in `test_cli.py`:

```python
# Change all input="2\n1\n" to input="2\n1\n\n"
# The extra \n confirms the mapping table
```

- [ ] **Step 8: Verify all pass**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest -v 2>&1 | tail -10
```

Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add patchport/cli.py tests/test_cli_v2.py tests/test_cli.py
git commit -m "feat: add mapping phase, --remap flag, and path translation to CLI"
```

---

## Task 9: README.md update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md**

Add a new section after "Quick Start" and update the CLI Reference. Replace the entire README with:

```markdown
# patchport

> Apply upstream Git changes to your local codebase — without sharing a repository.

[![PyPI version](https://badge.fury.io/py/patchport.svg)](https://pypi.org/project/patchport/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Problem

You and a collaborator maintain the same project in **separate, unlinked Git repositories** — perhaps because your environments, directory structures, or deployment targets differ too much to share a single remote.

Every time the upstream changes, you manually sift through their commits, re-apply relevant changes by hand, and pray nothing conflicts with your local customizations. This is exactly as tedious as it sounds.

## The Solution

`patchport` automates this in three steps:

1. Point it at the upstream repo and your local directory.
2. Choose which upstream commits to incorporate.
3. It builds a **file similarity map**, applies the diff via **3-way merge**, and inserts standard Git conflict markers where local and upstream diverge.

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

Because upstream and your local directory may have different structures or slightly different filenames, patchport scores every upstream↔local file pair by **filename similarity (30%)** and **content similarity (70%)**:

```
╭──────────────────────────────────────────────────────────────────────────╮
│ File Mapping Candidates                                                  │
├───┬──────────────────────────┬───────────────────────────┬──────────────┤
│ # │ Upstream file            │ Your file (suggested)     │ Confidence   │
├───┼──────────────────────────┼───────────────────────────┼──────────────┤
│ 1 │ src/audio/encoder.py     │ lib/audio/encoder_v2.py   │  94%         │
│ 2 │ src/config.py            │ config/config_mgr.py      │  88%         │
│ 3 │ assets/logo.png          │ assets/logo.png           │ [binary — overwrite] │
│ 4 │ src/win32/driver.py      │ (unmapped — skip)         │  11%         │
╰───┴──────────────────────────┴───────────────────────────┴──────────────╯

Edit a mapping? Enter row number to change, or press Enter to confirm all:
```

Enter a row number to change an individual mapping, or press Enter to accept all suggestions. The confirmed mapping is saved to `.patchport-map.json` and reused on subsequent runs.

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

- **String value** → target file path (text merge via 3-way merge)
- **`null`** → explicitly skipped (no merge, no overwrite)
- **Object with `"binary": true`** → binary file with explicit action

Subsequent runs load this file automatically — no re-confirmation needed. If upstream adds new files not in the map, patchport runs similarity check only for those files and updates the map.

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
                     Does not save the mapping file.
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
| Filename similarity | 30% | `SequenceMatcher` on the basename only (ignores path) |
| Content similarity | 70% | `SequenceMatcher` on the full file text |

Files scoring below 0.5 are listed as **unmapped** and skipped by default. Binary files (containing null bytes) skip content comparison and are overwritten by default.

No external libraries required — patchport uses Python's built-in `difflib` module.

---

## Security

- All Git commands use `subprocess` with explicit argument lists — no `shell=True`.
- User-supplied target paths are validated to exist within `--target` before saving.
- No credentials, tokens, or `.env` files are read or written.
- No network access — patchport operates entirely on the local filesystem.
- `.patchport-map.json` is parsed with `json.loads()` — no `eval()`.

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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for v2 file similarity mapping workflow"
```

---

## Task 10: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd /home/gene/Github/convert && .venv/bin/pytest -v
```

Expected: all tests pass

- [ ] **Step 2: Check CLI version and help**

```bash
cd /home/gene/Github/convert && .venv/bin/patchport --version
cd /home/gene/Github/convert && .venv/bin/patchport --help
```

Expected: version 0.1.0, all options shown including `--remap`

- [ ] **Step 3: Bump version to 0.2.0**

Update `pyproject.toml`:
```toml
version = "0.2.0"
```

Update `patchport/__init__.py`:
```python
__version__ = "0.2.0"
```

- [ ] **Step 4: Build wheel**

```bash
cd /home/gene/Github/convert && .venv/bin/python -m build --wheel 2>&1 | tail -3
ls dist/
```

Expected: `patchport-0.2.0-py3-none-any.whl`

- [ ] **Step 5: Final commit and push**

```bash
git add pyproject.toml patchport/__init__.py
git commit -m "chore: bump version to 0.2.0"
git push
```
