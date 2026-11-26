"""Typed assurance arguments and fail-closed defeater assessment.

This module records argument structure; it does not infer proposition truth or
make audit/authorization decisions.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple
from .contracts import FreshnessStatus

class AssuranceContractError(ValueError):
    pass

def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssuranceContractError(f"{field} must be a non-empty string")
    return value.strip()

def _ids(values: tuple[str, ...], field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise AssuranceContractError(f"{field} must be an immutable tuple")
    result = tuple(_text(value, field) for value in values)
    if len(result) != len(set(result)):
        raise AssuranceContractError(f"{field} must not contain duplicates")
    if required and not result:
        raise AssuranceContractError(f"{field} must not be empty")
    return result

class ArgumentRelation(str, Enum):
    SUPPORTS = "supports"
    CHALLENGES = "challenges"

class DefeaterKind(str, Enum):
    REBUTTING = "rebutting"
    UNDERCUTTING = "undercutting"

class DefeaterAction(str, Enum):
    RESPOND = "respond"
    RESOLVE = "resolve"
    ACCEPT_RESIDUAL = "accept_residual"

class ArgumentAssessment(str, Enum):
    NO_ARGUMENT = "no_argument"
    INCOMPLETE = "incomplete"
    CONTESTED = "contested"
    SUPPORTS_WITH_OPEN_DEFEATERS = "supports_with_open_defeaters"
    SUPPORTS_WITHOUT_OPEN_DEFEATERS = "supports_without_open_defeaters"

@dataclass(frozen=True)
class AssuranceClaim:
    claim_id: str
    proposition_id: str
    subject_id: str
    scope_id: str
    source_snapshot_id: str
    statement: str
    def __post_init__(self):
        for name in ("claim_id", "proposition_id", "subject_id", "scope_id", "source_snapshot_id", "statement"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

@dataclass(frozen=True)
class ArgumentLink:
    link_id: str
    claim_id: str
    relation: ArgumentRelation
    premise_ids: Tuple[str, ...]
    warrant_id: str
    evidence_ids: Tuple[str, ...]
    provenance_node_ids: Tuple[str, ...]
    def __post_init__(self):
        for name in ("link_id", "claim_id", "warrant_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.relation, ArgumentRelation):
            raise AssuranceContractError("relation must be an ArgumentRelation")
        for name in ("premise_ids", "evidence_ids", "provenance_node_ids"):
            object.__setattr__(self, name, _ids(getattr(self, name), name, required=True))

@dataclass(frozen=True)
class Defeater:
    defeater_id: str
    claim_id: str
    kind: DefeaterKind
    target_link_id: str | None
    description: str
    evidence_ids: Tuple[str, ...]
    def __post_init__(self):
        for name in ("defeater_id", "claim_id", "description"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.kind, DefeaterKind):
            raise AssuranceContractError("kind must be a DefeaterKind")
        if self.kind is DefeaterKind.UNDERCUTTING and self.target_link_id is None:
            raise AssuranceContractError("an undercutting defeater must identify the inference link it undercuts")
        if self.target_link_id is not None:
            object.__setattr__(self, "target_link_id", _text(self.target_link_id, "target_link_id"))
        object.__setattr__(self, "evidence_ids", _ids(self.evidence_ids, "evidence_ids", required=True))

@dataclass(frozen=True)
class DefeaterEvent:
    event_id: str
    defeater_id: str
    action: DefeaterAction
    rationale: str
    evidence_ids: Tuple[str, ...] = ()
    authorized_by: str | None = None
    def __post_init__(self):
        for name in ("event_id", "defeater_id", "rationale"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.action, DefeaterAction):
            raise AssuranceContractError("action must be a DefeaterAction")
        object.__setattr__(self, "evidence_ids", _ids(self.evidence_ids, "evidence_ids"))
        if self.action is DefeaterAction.RESOLVE and not self.evidence_ids:
            raise AssuranceContractError("resolving a defeater requires response evidence")
        if self.action is DefeaterAction.ACCEPT_RESIDUAL:
            object.__setattr__(self, "authorized_by", _text(self.authorized_by, "authorized_by"))

def evaluate_assurance(
    claim: AssuranceClaim,
    links: tuple[ArgumentLink, ...],
    defeaters: tuple[Defeater, ...],
    events: tuple[DefeaterEvent, ...],
    *,
    available_evidence_ids: frozenset[str],
    freshness: Mapping[str, FreshnessStatus],
) -> ArgumentAssessment:
    """Assess argument completeness, not proposition truth.

    Only explicit RESOLVE events with available response evidence close a defeater.
    ACCEPT_RESIDUAL records an authorized disposition but does not prove the
    objection false or remove it from the historical argument.
    """
    if not isinstance(claim, AssuranceClaim):
        raise TypeError("claim must be an AssuranceClaim")
    if not all(isinstance(x, ArgumentLink) and x.claim_id == claim.claim_id for x in links):
        raise AssuranceContractError("all argument links must target the supplied claim")
    if not all(isinstance(x, Defeater) and x.claim_id == claim.claim_id for x in defeaters):
        raise AssuranceContractError("all defeaters must target the supplied claim")
    if not isinstance(available_evidence_ids, frozenset):
        raise AssuranceContractError("available_evidence_ids must be a frozenset")
    if not links:
        return ArgumentAssessment.NO_ARGUMENT
    if len({x.link_id for x in links}) != len(links) or len({x.defeater_id for x in defeaters}) != len(defeaters):
        raise AssuranceContractError("link and defeater identities must be unique")
    link_ids = {x.link_id for x in links}
    for item in defeaters:
        if item.kind is DefeaterKind.UNDERCUTTING and item.target_link_id not in link_ids:
            raise AssuranceContractError("undercutting defeater targets an unknown argument link")
    for item in links:
        if not set(item.evidence_ids).issubset(available_evidence_ids):
            return ArgumentAssessment.INCOMPLETE
        if any(freshness.get(node) is not FreshnessStatus.FRESH for node in item.provenance_node_ids):
            return ArgumentAssessment.INCOMPLETE
    if any(not set(x.evidence_ids).issubset(available_evidence_ids) for x in defeaters):
        return ArgumentAssessment.INCOMPLETE
    histories: dict[str, list[DefeaterEvent]] = {x.defeater_id: [] for x in defeaters}
    seen: set[str] = set()
    for event in events:
        if event.defeater_id not in histories:
            raise AssuranceContractError("defeater event references an unknown defeater")
        if event.event_id in seen:
            raise AssuranceContractError("defeater event IDs must be unique")
        seen.add(event.event_id)
        histories[event.defeater_id].append(event)
    open_items = []
    for item in defeaters:
        history = histories[item.defeater_id]
        if not history:
            open_items.append(item)
            continue
        last = history[-1]
        if last.action is DefeaterAction.RESOLVE:
            if not set(last.evidence_ids).issubset(available_evidence_ids):
                return ArgumentAssessment.INCOMPLETE
        else:
            open_items.append(item)
    if any(x.relation is ArgumentRelation.CHALLENGES for x in links):
        return ArgumentAssessment.CONTESTED
    if not any(x.relation is ArgumentRelation.SUPPORTS for x in links):
        return ArgumentAssessment.NO_ARGUMENT
    if open_items:
        return ArgumentAssessment.SUPPORTS_WITH_OPEN_DEFEATERS
    return ArgumentAssessment.SUPPORTS_WITHOUT_OPEN_DEFEATERS
