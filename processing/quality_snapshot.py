from dataclasses import dataclass


@dataclass(frozen=True)
class QualitySnapshot:
    run_id: str
    status: str
    error_count: int
    warning_count: int
