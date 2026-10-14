"""Recursive read-only JSON-compatible evidence values.

Preserves JSON value semantics at the serialization boundary while preventing
mutations of nested receipt/finding state after a receipt has been sealed.
"""
from collections.abc import Mapping
from types import MappingProxyType


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    raise TypeError(f'Unsupported nested evidence value: {type(value).__name__}')


def thaw(value):
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(v) for v in value]
    return value
