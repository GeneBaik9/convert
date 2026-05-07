from patchport.mapper import MappingCandidate, is_binary, compute_score, build_candidates


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
