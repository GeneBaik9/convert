from patchport.mapper import MappingCandidate, is_binary, compute_score


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
