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
