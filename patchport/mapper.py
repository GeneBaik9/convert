from dataclasses import dataclass


@dataclass
class MappingCandidate:
    upstream_path: str
    target_path: str | None     # None = unmapped/skip
    score: float                # 0.0 to 1.0
    is_binary: bool
    action: str                 # "merge" | "overwrite" | "skip"
