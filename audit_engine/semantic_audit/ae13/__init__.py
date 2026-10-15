"""AE-13 pre-implementation D1/D2/D3 design-validation bridge.

No authority to approve code, to execute untrusted code, or to reinterpret
legacy classifications as verified findings. Explicit opt-in only.
"""
from .legacy import adapt_legacy, validate_legacy_report
from .bindings import admit_analysis, create_obligation, run_bound_verification
from .benchmark import benchmark_relations
__all__ = ('adapt_legacy', 'validate_legacy_report', 'admit_analysis',
           'create_obligation', 'run_bound_verification', 'benchmark_relations')
