from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationConstraint:
    category: str
    instruction: str
    priority: str = "normal"
