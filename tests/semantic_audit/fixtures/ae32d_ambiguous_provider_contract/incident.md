# Incomplete provider-contract evidence

The visible extractor reads provider.total_calls and the visible adapter
maintains self.calls. The factory delegates construction to runtime_provider,
whose implementation and package metadata are not included in this evidence
bundle. Dynamic wrappers, inheritance, generated attributes, and the concrete
provider class therefore cannot be ruled in or out.

The correct bounded response is to report the visible mismatch as an
unresolved hypothesis and abstain from asserting a runtime defect until the
missing provider implementation and runtime path are supplied.
