"""Canvas geometry, held outside the tracked flow artifact.

``flow.json`` carries no coordinates. ``layout.json`` carries nothing else.
Deploying to NiFi means parse, :func:`apply_layout`, POST.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from pydantic import BaseModel

from .models import Position, VersionedProcessGroup

#: Attributes moved to the sidecar. Matches the VOLATILE geometry fields.
GEOMETRY = ("position", "bends", "width", "height", "z_index", "label_index", "style")

COL_WIDTH = 550.0
ROW_HEIGHT = 240.0
PAD_X = 120.0
PAD_Y = 100.0

#: Background colour per component name prefix.
PALETTE = {
    "IN_": "#CCE5FF",
    "PRC_": "#E2E3E5",
    "SUB_": "#E2D9F3",
    "OUT_": "#D4EDDA",
    "ERR_": "#F8D7DA",
}
DEFAULT_PREFIX = "PRC_"


def _walk(node: Any, visit) -> None:
    if isinstance(node, BaseModel):
        visit(node)
        for name in type(node).model_fields:
            _walk(getattr(node, name), visit)
    elif isinstance(node, list):
        for item in node:
            _walk(item, visit)
    elif isinstance(node, dict):
        for item in node.values():
            _walk(item, visit)


def extract_layout(model: BaseModel) -> dict[str, dict[str, Any]]:
    """Collect geometry from a parsed flow, keyed by component identifier."""
    layout: dict[str, dict[str, Any]] = {}

    def visit(node: BaseModel) -> None:
        identifier = getattr(node, "identifier", None)
        if not identifier:
            return
        entry: dict[str, Any] = {}
        for attr in GEOMETRY:
            value = getattr(node, attr, None)
            if value in (None, [], {}, 0, 0.0):
                continue
            if isinstance(value, BaseModel):
                entry[attr] = value.model_dump()
            elif isinstance(value, list):
                entry[attr] = [v.model_dump() if isinstance(v, BaseModel) else v for v in value]
            else:
                entry[attr] = value
        if entry:
            layout[identifier] = entry

    _walk(model, visit)
    return {k: layout[k] for k in sorted(layout)}


def apply_layout(model: BaseModel, layout: dict[str, dict[str, Any]]) -> None:
    """Re-attach geometry in place. Call before sending a flow to NiFi."""

    def visit(node: BaseModel) -> None:
        entry = layout.get(getattr(node, "identifier", "") or "")
        if not entry:
            return
        for attr, value in entry.items():
            if attr == "position":
                setattr(node, attr, Position(**value))
            elif attr == "bends":
                setattr(node, attr, [Position(**b) for b in value])
            else:
                setattr(node, attr, value)

    _walk(model, visit)


def rank(node_ids: Iterable[str], edges: Iterable[tuple[str, str]]) -> dict[str, int]:
    """Longest-path layering.

    Cycles saturate at the pass cap, so this always terminates and always
    returns the same ranks for the same input.
    """
    ranks = {node_id: 0 for node_id in sorted(node_ids)}
    kept = sorted({(s, d) for s, d in edges if s != d and s in ranks and d in ranks})
    for _ in range(len(ranks)):
        changed = False
        for src, dst in kept:
            if ranks[dst] < ranks[src] + 1:
                ranks[dst] = ranks[src] + 1
                changed = True
        if not changed:
            break
    return ranks


def _prefix(name: Optional[str]) -> str:
    upper = (name or "").upper()
    return next((p for p in PALETTE if upper.startswith(p)), DEFAULT_PREFIX)


def build_layout(group: VersionedProcessGroup) -> dict[str, dict[str, Any]]:
    """Generate geometry for a group and all of its children.

    Column comes from graph rank. Name prefix sets colour only. Row order
    comes from ``(rank, name, identifier)``, never from export order.
    """
    layout: dict[str, dict[str, Any]] = {}

    ids = {p.identifier for p in group.processors}
    ids |= {p.identifier for p in (*group.input_ports, *group.output_ports)}
    ids |= {f.identifier for f in group.funnels}
    ids |= {g.identifier for g in group.process_groups}
    edges = {(c.source.id, c.destination.id) for c in group.connections}
    ranks = rank(ids, edges)

    nodes: list[tuple[str, Optional[str], bool]] = [
        *((p.identifier, p.name, True) for p in group.processors),
        *((p.identifier, p.name, False) for p in (*group.input_ports, *group.output_ports)),
        *((f.identifier, f.name, False) for f in group.funnels),
        *((g.identifier, g.name, False) for g in group.process_groups),
    ]

    rows: dict[int, int] = {}
    for identifier, name, is_processor in sorted(
        nodes, key=lambda n: (ranks.get(n[0], 0), n[1] or "", n[0])
    ):
        column = ranks.get(identifier, 0)
        row = rows.get(column, 0)
        rows[column] = row + 1
        entry: dict[str, Any] = {
            "position": {"x": PAD_X + column * COL_WIDTH, "y": PAD_Y + row * ROW_HEIGHT}
        }
        if is_processor:
            entry["style"] = {"background-color": PALETTE[_prefix(name)]}
        layout[identifier] = entry

    for child in group.process_groups:
        layout.update(build_layout(child))

    return {k: layout[k] for k in sorted(layout)}
