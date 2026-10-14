"""AE-03: bounded, provenance-aware test-oracle mutation assessment.

Public API deliberately distinguishes source-witness verification from
execution-outcome replay and prohibits in-place mutation of source checkout.
"""
from .source import Mutation, discover, verify_mutation
from .runner import run_experiment, verify_record
from .impact import VerifiedImpact, verified_impact

__all__ = ['Mutation', 'discover', 'verify_mutation', 'run_experiment',
           'verify_record', 'VerifiedImpact', 'verified_impact']
