# patchport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `patchport`, a pip-installable CLI that extracts a git diff between two selected commits in an upstream repository and applies it to a separate local codebase via per-file 3-way merge.

**Architecture:** Five focused modules under `patchport/` — `git.py` (read-only git queries), `patcher.py` (per-file `git merge-file` orchestration), `reporter.py` (Rich terminal output), `cli.py` (Click entry point + interactive commit selection), `exceptions.py` (domain errors). No shared mutable state between modules.

**Tech Stack:** Python 3.9+, Click 8, Rich 13, pytest, hatchling (build), git 2.x (system dependency)

---

## File Map

| File | Role |
|---|---|
| `pyproject.toml` | Package metadata, entry point, dependencies |
| `patchport/__init__.py` | Version constant |
| `patchport/exceptions.py` | `NotAGitRepoError`, `InvalidCommitRangeError`, `PatchApplicationError` |
| `patchport/git.py` | `list_commits()`, `get_changed_files()`, `show_file_at_commit()` |
| `patchport/patcher.py` | `FileResult` dataclass, `apply_changes()`, `_merge_file()` |
| `patchport/reporter.py` | `print_commit_table()`, `print_results()`, `console` |
| `patchport/cli.py` | `main()` Click command — orchestrates all modules |
| `tests/test_git.py` | Unit tests for git.py (real temp repos) |
| `tests/test_patcher.py` | Unit tests for patcher.py (real temp repos) |
| `tests/test_reporter.py` | Unit tests for reporter.py (output capture) |
| `tests/test_cli.py` | End-to-end integration test via Click test runner |
| `README.md` | PyPI / GitHub documentation |
| `.gitignore` | Python standard ignores |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `patchport/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p patchport tests
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "patchport"
version = "0.1.0"
description = "Apply upstream Git changes to your local codebase — without sharing a repository."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.9"
authors = [{ name = "Gene Baik", email = "jongmin.baik@gmail.com" }]
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Environment :: Console",
    "Topic :: Software Development :: Version Control :: Git",
]
dependencies = [
    "click>=8.0",
    "rich>=13.0",
]

[project.scripts]
patchport = "patchport.cli:main"

[project.urls]
Homepage = "https://github.com/GeneBaik9/convert"
Repository = "https://github.com/GeneBaik9/convert"
Issues = "https://github.com/GeneBaik9/convert/issues"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `patchport/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Write `tests/__init__.py`**

```python
```

(empty file)

- [ ] **Step 5: Write `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
.pytest_cache/
*.tmp
```

- [ ] **Step 6: Install in editable mode**

```bash
pip install -e ".[dev]" 2>/dev/null || pip install -e .
pip install pytest
```

- [ ] **Step 7: Verify import works**

```bash
python -c "import patchport; print(patchport.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml patchport/__init__.py tests/__init__.py .gitignore
git commit -m "chore: scaffold patchport package"
```

---

## Task 2: Custom Exceptions

**Files:**
- Create: `patchport/exceptions.py`

- [ ] **Step 1: Write `patchport/exceptions.py`**

```python
from pathlib import Path


class NotAGitRepoError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Not a Git repository: {path}")
        self.path = path


class InvalidCommitRangeError(Exception):
    def __init__(self, from_hash: str, to_hash: str) -> None:
        super().__init__(
            f"Invalid commit range: {from_hash[:7]}..{to_hash[:7]}. "
            "'From' must be an older commit than 'To'."
        )


class PatchApplicationError(Exception):
    def __init__(self, file_path: str, detail: str) -> None:
        super().__init__(f"Failed to apply patch to '{file_path}': {detail}")
        self.file_path = file_path
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from patchport.exceptions import NotAGitRepoError, InvalidCommitRangeError, PatchApplicationError; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add patchport/exceptions.py
git commit -m "feat: add custom exception classes"
```

---

## Task 3: git.py — Commit Listing

**Files:**
- Create: `patchport/git.py`
- Create: `tests/test_git.py`

- [ ] **Step 1: Write the failing tests for `list_commits`**

```python
# tests/test_git.py
import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits
from patchport.exceptions import NotAGitRepoError


@pytest.fixture
def upstream_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    (repo / "main.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump x to 2"], cwd=repo, check=True, capture_output=True)
    return repo


def test_list_commits_returns_newest_first(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    assert commits[0]["message"] == "bump x to 2"
    assert commits[1]["message"] == "initial commit"


def test_list_commits_fields(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    c = commits[0]
    assert "index" in c
    assert "hash" in c
    assert "short_hash" in c
    assert "message" in c
    assert "date" in c
    assert c["index"] == 1
    assert len(c["hash"]) == 40
    assert len(c["short_hash"]) == 7


def test_list_commits_limit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo, limit=1)
    assert len(commits) == 1
    assert commits[0]["message"] == "bump x to 2"


def test_list_commits_raises_for_non_repo(tmp_path: Path) -> None:
    with pytest.raises(NotAGitRepoError):
        list_commits(tmp_path / "not_a_repo")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_git.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` (git.py doesn't exist yet)

- [ ] **Step 3: Write `patchport/git.py` — `list_commits` only**

```python
import subprocess
from pathlib import Path
from .exceptions import NotAGitRepoError


def list_commits(upstream: Path, limit: int = 20) -> list[dict]:
    result = subprocess.run(
        [
            "git", "log",
            f"--max-count={limit}",
            "--format=%H\x1f%s\x1f%ad",
            "--date=short",
        ],
        cwd=upstream,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise NotAGitRepoError(upstream)
    lines = [l for l in result.stdout.strip().splitlines() if l]
    commits = []
    for i, line in enumerate(lines, 1):
        hash_, message, date = line.split("\x1f", 2)
        commits.append(
            {
                "index": i,
                "hash": hash_,
                "short_hash": hash_[:7],
                "message": message,
                "date": date,
            }
        )
    return commits
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_git.py::test_list_commits_returns_newest_first \
       tests/test_git.py::test_list_commits_fields \
       tests/test_git.py::test_list_commits_limit \
       tests/test_git.py::test_list_commits_raises_for_non_repo -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/git.py tests/test_git.py
git commit -m "feat: implement list_commits with tests"
```

---

## Task 4: git.py — File Operations

**Files:**
- Modify: `patchport/git.py`
- Modify: `tests/test_git.py`

- [ ] **Step 1: Add failing tests for `get_changed_files` and `show_file_at_commit`**

Append to `tests/test_git.py`:

```python
from patchport.git import list_commits, get_changed_files, show_file_at_commit


def test_get_changed_files(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    from_hash = commits[1]["hash"]  # older
    to_hash = commits[0]["hash"]    # newer
    files = get_changed_files(upstream_repo, from_hash, to_hash)
    assert files == ["main.py"]


def test_get_changed_files_empty_range(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    same = commits[0]["hash"]
    files = get_changed_files(upstream_repo, same, same)
    assert files == []


def test_show_file_at_older_commit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    older_hash = commits[1]["hash"]
    content = show_file_at_commit(upstream_repo, older_hash, "main.py")
    assert content == "x = 1\n"


def test_show_file_at_newer_commit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    newer_hash = commits[0]["hash"]
    content = show_file_at_commit(upstream_repo, newer_hash, "main.py")
    assert content == "x = 2\n"


def test_show_file_returns_none_for_missing_file(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    result = show_file_at_commit(upstream_repo, commits[0]["hash"], "nonexistent.py")
    assert result is None
```

- [ ] **Step 2: Run tests — verify new ones fail**

```bash
pytest tests/test_git.py -v
```

Expected: 4 pass (existing), 5 fail (new)

- [ ] **Step 3: Add `get_changed_files` and `show_file_at_commit` to `patchport/git.py`**

Append to the existing `patchport/git.py`:

```python

def get_changed_files(upstream: Path, from_hash: str, to_hash: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{from_hash}..{to_hash}"],
        cwd=upstream,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        from .exceptions import InvalidCommitRangeError
        raise InvalidCommitRangeError(from_hash, to_hash)
    return [f for f in result.stdout.strip().splitlines() if f]


def show_file_at_commit(upstream: Path, commit_hash: str, file_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{file_path}"],
        cwd=upstream,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout
```

- [ ] **Step 4: Run all git tests — verify all pass**

```bash
pytest tests/test_git.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/git.py tests/test_git.py
git commit -m "feat: implement get_changed_files and show_file_at_commit"
```

---

## Task 5: patcher.py

**Files:**
- Create: `patchport/patcher.py`
- Create: `tests/test_patcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_patcher.py
import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits
from patchport.patcher import apply_changes, FileResult


@pytest.fixture
def repos(tmp_path: Path):
    """Upstream with 2 commits; target with local modifications."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    # Commit 1 (older): version=1, feature=False
    (upstream / "app.py").write_text("version = 1\nfeature = False\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    # Commit 2 (newer): version=2, feature=True
    (upstream / "app.py").write_text("version = 2\nfeature = True\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    # Local file matches old upstream on 'version', has own value for 'feature'
    (target / "app.py").write_text("version = 1\nfeature = 'my_override'\n")

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]  # older
    to_hash = commits[0]["hash"]    # newer
    return upstream, target, from_hash, to_hash


@pytest.fixture
def clean_repos(tmp_path: Path):
    """Upstream with 2 commits; target has no local divergence."""
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
    (target / "app.py").write_text("x = 1\n")  # identical to old upstream

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]
    to_hash = commits[0]["hash"]
    return upstream, target, from_hash, to_hash


def test_clean_merge_updates_file(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    results = apply_changes(upstream, target, from_hash, to_hash)
    assert len(results) == 1
    assert results[0].path == "app.py"
    assert results[0].status == "patched"
    assert (target / "app.py").read_text() == "x = 2\n"


def test_conflict_inserts_markers(repos):
    upstream, target, from_hash, to_hash = repos
    results = apply_changes(upstream, target, from_hash, to_hash)
    assert len(results) == 1
    result = results[0]
    assert result.status == "conflict"
    assert result.conflict_count >= 1
    content = (target / "app.py").read_text()
    assert "<<<<<<< " in content
    assert "=======" in content
    assert ">>>>>>> " in content


def test_new_file_is_created(tmp_path: Path):
    """A file added in upstream is created in target."""
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
    results = apply_changes(upstream, target, commits[1]["hash"], commits[0]["hash"])

    new_file_result = next(r for r in results if r.path == "new.py")
    assert new_file_result.status == "patched"
    assert (target / "new.py").read_text() == "print('hello')\n"


def test_apply_changes_returns_list_of_file_results(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    results = apply_changes(upstream, target, from_hash, to_hash)
    assert isinstance(results, list)
    assert all(isinstance(r, FileResult) for r in results)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_patcher.py -v
```

Expected: `ImportError` (patcher.py doesn't exist)

- [ ] **Step 3: Write `patchport/patcher.py`**

```python
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import PatchApplicationError
from .git import get_changed_files, show_file_at_commit


@dataclass
class FileResult:
    path: str
    status: str  # "patched" | "conflict" | "skipped"
    conflict_count: int = 0


def apply_changes(
    upstream: Path, target: Path, from_hash: str, to_hash: str
) -> list[FileResult]:
    changed_files = get_changed_files(upstream, from_hash, to_hash)
    return [_merge_file(upstream, target, from_hash, to_hash, f) for f in changed_files]


def _merge_file(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    file_path: str,
) -> FileResult:
    old_content = show_file_at_commit(upstream, from_hash, file_path)
    new_content = show_file_at_commit(upstream, to_hash, file_path)
    local_file = target / file_path

    if new_content is None:
        return FileResult(path=file_path, status="skipped")

    if old_content is None or not local_file.exists():
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_text(new_content)
        return FileResult(path=file_path, status="patched")

    old_fd, old_path = tempfile.mkstemp(suffix=".base")
    new_fd, new_path = tempfile.mkstemp(suffix=".other")
    try:
        os.write(old_fd, old_content.encode())
        os.close(old_fd)
        os.write(new_fd, new_content.encode())
        os.close(new_fd)

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
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
pytest tests/test_patcher.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/patcher.py tests/test_patcher.py
git commit -m "feat: implement patcher with git merge-file and conflict detection"
```

---

## Task 6: reporter.py

**Files:**
- Create: `patchport/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reporter.py
from io import StringIO
from rich.console import Console
from patchport.patcher import FileResult
from patchport.reporter import print_results


def _capture_output(fn, *args) -> str:
    buf = StringIO()
    con = Console(file=buf, highlight=False, markup=False)
    fn(*args, con=con)
    return buf.getvalue()


def test_print_results_patched():
    results = [FileResult(path="foo.py", status="patched")]
    output = _capture_output(print_results, results)
    assert "foo.py" in output
    assert "patched" in output.lower()


def test_print_results_conflict():
    results = [FileResult(path="bar.py", status="conflict", conflict_count=2)]
    output = _capture_output(print_results, results)
    assert "bar.py" in output
    assert "2" in output


def test_print_results_skipped():
    results = [FileResult(path="gone.py", status="skipped")]
    output = _capture_output(print_results, results)
    assert "gone.py" in output
    assert "skip" in output.lower()


def test_print_results_summary_counts():
    results = [
        FileResult(path="a.py", status="patched"),
        FileResult(path="b.py", status="conflict", conflict_count=1),
        FileResult(path="c.py", status="patched"),
    ]
    output = _capture_output(print_results, results)
    assert "2" in output   # 2 patched
    assert "1" in output   # 1 conflict
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_reporter.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `patchport/reporter.py`**

```python
from rich.console import Console
from rich.table import Table
from rich import box

from .patcher import FileResult

console = Console()


def print_commit_table(commits: list[dict], con: Console | None = None) -> None:
    con = con or console
    table = Table(
        title="Commits in upstream",
        box=box.ROUNDED,
        show_lines=False,
        title_style="bold",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Hash", style="cyan", width=9)
    table.add_column("Message")
    table.add_column("Date", style="dim", width=12)
    for c in commits:
        table.add_row(str(c["index"]), c["short_hash"], c["message"], c["date"])
    con.print(table)


def print_results(
    results: list[FileResult], con: Console | None = None
) -> None:
    con = con or console
    for r in results:
        if r.status == "patched":
            con.print(f"  [green]✔[/green]  {r.path}    patched cleanly")
        elif r.status == "conflict":
            con.print(
                f"  [yellow]⚠[/yellow]  {r.path}    "
                f"{r.conflict_count} conflict(s) — resolve markers and re-run"
            )
        else:
            con.print(f"  [dim]–[/dim]  {r.path}    skipped (deleted upstream)")

    patched = sum(1 for r in results if r.status == "patched")
    conflicts = sum(1 for r in results if r.status == "conflict")

    con.print("\n" + "─" * 48)
    con.print(f"  {patched} file(s) patched  ·  {conflicts} conflict(s) found")

    if conflicts > 0:
        con.print(
            "\n[yellow]⚠  Resolve conflict markers above, then commit your changes.[/yellow]"
        )
```

Note: `print_results` accepts an optional `con` keyword arg for testability.

- [ ] **Step 4: Run tests — verify all pass**

```bash
pytest tests/test_reporter.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add patchport/reporter.py tests/test_reporter.py
git commit -m "feat: implement Rich-based reporter"
```

---

## Task 7: cli.py + Integration Test

**Files:**
- Create: `patchport/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the integration test first**

```python
# tests/test_cli.py
import subprocess
from pathlib import Path
import pytest
from click.testing import CliRunner
from patchport.cli import main


@pytest.fixture
def two_repos(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "hello.py").write_text("msg = 'hello'\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "hello.py").write_text("msg = 'world'\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update msg"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "hello.py").write_text("msg = 'hello'\n")
    return upstream, target


def test_cli_applies_clean_patch(two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",   # From #2 (older) → To #1 (newer)
    )
    assert result.exit_code == 0, result.output
    assert (target / "hello.py").read_text() == "msg = 'world'\n"


def test_cli_dry_run_does_not_modify(two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target), "--dry-run"],
        input="2\n1\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "hello.py").read_text() == "msg = 'hello'\n"  # unchanged
    assert "Dry run" in result.output


def test_cli_invalid_upstream_exits_with_error(tmp_path):
    # tmp_path exists but is not a git repo — exercises our NotAGitRepoError path
    target = tmp_path / "target"
    target.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(tmp_path), "--target", str(target)],
    )
    assert result.exit_code != 0


def test_cli_shows_commit_table(two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",
    )
    assert "initial" in result.output
    assert "update msg" in result.output
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `patchport/cli.py`**

```python
import sys
from pathlib import Path

import click

from .exceptions import NotAGitRepoError, PatchApplicationError
from .git import get_changed_files, list_commits
from .patcher import apply_changes
from .reporter import console, print_commit_table, print_results


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
@click.option(
    "--limit",
    default=20,
    show_default=True,
    help="Number of recent commits to display.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show which files would change without modifying anything.",
)
@click.version_option()
def main(upstream: Path, target: Path, limit: int, dry_run: bool) -> None:
    """Apply upstream Git changes to your local codebase — without sharing a repository.

    Displays recent commits from UPSTREAM, lets you select a range,
    then applies the diff to TARGET using per-file 3-way merge.
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

    console.print(f"\nApplying diff ({len(changed)} file(s) changed)...\n")

    if dry_run:
        for f in changed:
            console.print(f"  [dim]~[/dim]  {f}")
        console.print("\n[dim]Dry run — no files were modified.[/dim]")
        sys.exit(0)

    try:
        results = apply_changes(upstream, target, from_hash, to_hash)
    except PatchApplicationError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    print_results(results)
```

- [ ] **Step 4: Run all tests**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 5: Smoke test manually**

```bash
patchport --help
```

Expected: help text with `--upstream`, `--target`, `--limit`, `--dry-run` options

- [ ] **Step 6: Commit**

```bash
git add patchport/cli.py tests/test_cli.py
git commit -m "feat: implement CLI with interactive commit selection"
```

---

## Task 8: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
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

`patchport` automates this:

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
╭──────────────────────────────────────────────────────╮
│ Commits in upstream                                  │
├────┬─────────┬──────────────────────────┬────────────┤
│  # │ Hash    │ Message                  │ Date       │
├────┼─────────┼──────────────────────────┼────────────┤
│  1 │ a1b2c3d │ Fix audio sync issue     │ 2026-05-06 │
│  2 │ e4f5g6h │ Add subtitle support     │ 2026-05-04 │
│  3 │ i7j8k9l │ Refactor encoder logic   │ 2026-05-01 │
╰────┴─────────┴──────────────────────────┴────────────╘

From commit [#]: 3
To commit   [#]: 1

Applying diff (3 files changed)...

  ✔  encoder.py     patched cleanly
  ✔  subtitle.py    patched cleanly
  ⚠  config.py      2 conflict(s) — resolve markers and re-run

────────────────────────────────────────────────────────
  2 file(s) patched  ·  1 conflict(s) found

⚠  Resolve conflict markers above, then commit your changes.
```

Files with conflicts receive standard Git markers:

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
- Paths are validated and resolved to absolute before use.
- No credentials, tokens, or `.env` files are read or written.
- No network access — `patchport` is entirely local.

---

## Contributing

```bash
git clone https://github.com/GeneBaik9/convert.git
cd convert
pip install -e .
pip install pytest
pytest
```

Pull requests welcome. Please include tests for new behavior.

---

## License

MIT © Gene Baik
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add professional README for PyPI and GitHub"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass, zero warnings about missing fixtures

- [ ] **Step 2: Verify CLI entry point**

```bash
patchport --version
```

Expected: `patchport, version 0.1.0`

- [ ] **Step 3: Verify package builds cleanly**

```bash
pip install build
python -m build --wheel
ls dist/
```

Expected: `patchport-0.1.0-py3-none-any.whl`

- [ ] **Step 4: Final commit**

```bash
git add -A
git status   # confirm only expected files
git commit -m "chore: verify build artifacts" --allow-empty
```

---

## Out of Scope (v1.0)

- Storing last-synced commit state (planned v1.1)
- Binary file merging
- Remote upstream paths
- PyPI publish (run `twine upload dist/*` when ready)
