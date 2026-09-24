from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityContract:
    name: str
    provides: tuple[str, ...]
    depends_on: tuple[str, ...]
