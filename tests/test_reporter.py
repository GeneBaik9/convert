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
