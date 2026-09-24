from .quality_snapshot import QualitySnapshot


def compare_snapshots(previous, current):
    return {
        "new_errors": current.error_count - previous.error_count,
        "new_warnings": current.warning_count - previous.warning_count,
        "status_changed": previous.status != current.status,
    }
