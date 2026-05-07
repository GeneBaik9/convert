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
