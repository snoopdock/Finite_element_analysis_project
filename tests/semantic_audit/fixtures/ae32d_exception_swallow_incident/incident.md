# Exception-handling defect candidate

The declared contract requires an OSError from the supplied reader to propagate
to the caller. Inspect whether load_config preserves or suppresses that failure.
The helper failing_reader deterministically raises OSError.
