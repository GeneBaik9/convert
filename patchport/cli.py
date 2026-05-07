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
from .mapper_ui import show_mapping_ui
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
@click.option("--limit", default=20, show_default=True, help="Number of recent commits to display.")
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying anything.")
@click.option(
    "--remap",
    is_flag=True,
    help="Ignore saved mapping and rebuild from scratch. "
    "Backs up existing .patchport-map.json to .patchport-map.json.bak.",
)
@click.version_option()
def main(upstream: Path, target: Path, limit: int, dry_run: bool, remap: bool) -> None:
    """Apply upstream Git changes to your local codebase — without sharing a repository.

    Displays recent commits from UPSTREAM, lets you select a range, then opens
    a browser-based file mapping interface before applying changes to TARGET via
    per-file 3-way merge.  Conflict markers are inserted where local and upstream
    diverge.
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

    candidates = _resolve_candidates(
        upstream, target, from_hash, to_hash, changed, remap, dry_run
    )

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
                    "not in saved map — opening browser to update mapping..."
                )
                new_candidates = _build_and_confirm(
                    upstream, target, from_hash, to_hash, new_files, dry_run
                )
                if not dry_run:
                    save_map(target, saved + new_candidates)
                return saved + new_candidates
            return saved

    candidates = _build_and_confirm(
        upstream, target, from_hash, to_hash, changed_files, dry_run
    )
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
    console.print(f"\nAnalyzing file similarity ({len(changed_files)} file(s))...\n")

    upstream_files: dict[str, bytes] = {}
    for f in changed_files:
        raw = show_file_bytes_at_commit(upstream, from_hash, f)
        if raw is None:
            raw = show_file_bytes_at_commit(upstream, to_hash, f)
        if raw is not None:
            upstream_files[f] = raw

    target_files: dict[str, bytes] = {}
    target_file_list: list[str] = []
    for p in target.rglob("*"):
        if p.is_file() and p.name not in (".patchport-map.json", ".patchport-map.json.bak"):
            rel = str(p.relative_to(target))
            target_file_list.append(rel)
            try:
                target_files[rel] = p.read_bytes()
            except OSError:
                pass

    candidates = build_candidates(upstream_files, target_files)

    if dry_run:
        return candidates

    console.print("Opening browser for file mapping confirmation...\n")
    return show_mapping_ui(candidates, target_file_list)
