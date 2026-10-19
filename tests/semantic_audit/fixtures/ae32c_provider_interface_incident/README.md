# Controlled provider-interface incident fixture

This fixture represents a historical class of failure: an extraction consumer
reads `provider.total_calls`, while the provider adapter exposes a differently
named counter (`calls`). It is intentionally minimal and is never executed by
the auditor. AE-32C should discover the relationship through source, graph,
test-reference, and workflow evidence rather than receiving a prescribed list
of files or a prescribed correction.

The fixture is evaluation data, not production code and not a claim that the
current repository still contains this defect.
