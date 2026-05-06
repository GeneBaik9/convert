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
