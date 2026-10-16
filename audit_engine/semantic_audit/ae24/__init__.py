"""AE-24 language-agnostic semantic contracts and source-bound graph admission."""
from .contracts import SCHEMA, ContractError, Admission, admit, verify_admission, to_graph_assertions, canonical, sha
