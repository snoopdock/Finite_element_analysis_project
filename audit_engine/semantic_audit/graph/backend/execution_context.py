from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class BackendExecutionContext:

    graph: Any

    task_type: str = "general"

    preserve_metadata: bool = True

    provenance_tracking: bool = False

    validation_mode: bool = False

    options: Dict[str, Any] = field(default_factory=dict)
