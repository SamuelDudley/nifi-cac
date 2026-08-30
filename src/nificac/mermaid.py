"""Mermaid flowchart generation for documentation.

Output is deterministic: the same sort keys as :mod:`nificac.canonical`, so
``flow.mmd`` diffs as cleanly as ``flow.json``.

Limits:
  - Mermaid's layout degrades past roughly 50 nodes. Use ``per_group`` for
    large flows and link the diagrams together.
  - Node placement is not controllable and will not match the NiFi canvas.
  - Properties do not fit. This renders topology only.
"""

from __future__ import annotations

import re
from typing import Optional

from .layout import PALETTE
from .models import VersionedProcessGroup

DEFAULT_CLASS = "prc"


def _node_id(identifier: str) -> str:
    return "n" + re.sub(r"[^0-9a-zA-Z]", "", identifier)


def _label(text: Optional[str]) -> str:
    return (text or "").replace('"', "'")


def _class_of(name: Optional[str]) -> str:
    upper = (name or "").upper()
    return next(
        (p.rstrip("_").lower() for p in PALETTE if upper.startswith(p)), DEFAULT_CLASS
    )


def to_mermaid(group: VersionedProcessGroup, direction: str = "LR") -> str:
    """Render a group and its children as one flowchart."""
    lines = [f"flowchart {direction}"]
    for prefix, colour in PALETTE.items():
        lines.append(
            f"  classDef {prefix.rstrip('_').lower()} "
            f"fill:{colour},stroke:#495057,color:#212529"
        )
    styling: list[str] = []

    def emit(node: VersionedProcessGroup, depth: int) -> None:
        pad = "  " * (depth + 1)
        for processor in sorted(node.processors, key=lambda p: (p.name or "", p.identifier)):
            lines.append(f'{pad}{_node_id(processor.identifier)}["{_label(processor.name)}"]')
            styling.append(f"  class {_node_id(processor.identifier)} {_class_of(processor.name)}")
        for port in sorted(
            (*node.input_ports, *node.output_ports), key=lambda p: (p.type, p.name or "")
        ):
            lines.append(f'{pad}{_node_id(port.identifier)}[/"{_label(port.name)}"/]')
        for funnel in sorted(node.funnels, key=lambda f: f.identifier):
            lines.append(f"{pad}{_node_id(funnel.identifier)}(( ))")
        for child in sorted(node.process_groups, key=lambda g: (g.name or "", g.identifier)):
            lines.append(f'{pad}subgraph {_node_id(child.identifier)}["{_label(child.name)}"]')
            lines.append(f"{pad}  direction {direction}")
            emit(child, depth + 1)
            lines.append(f"{pad}end")
        for connection in sorted(
            node.connections,
            key=lambda c: (c.source.id, c.destination.id, tuple(c.selected_relationships)),
        ):
            labels = ", ".join(r for r in sorted(connection.selected_relationships) if r)
            arrow = f'-- "{labels}" -->' if labels else "-->"
            lines.append(
                f"{pad}{_node_id(connection.source.id)} {arrow} "
                f"{_node_id(connection.destination.id)}"
            )

    emit(group, 0)
    return "\n".join(lines + styling) + "\n"


def _descendant_ids(group: VersionedProcessGroup) -> set[str]:
    ids = {c.identifier for c in (*group.processors, *group.funnels)}
    ids |= {p.identifier for p in (*group.input_ports, *group.output_ports)}
    for child in group.process_groups:
        ids |= _descendant_ids(child) | {child.identifier}
    return ids


def to_mermaid_shallow(group: VersionedProcessGroup, direction: str = "LR") -> str:
    """Render one group. Child groups collapse to a single node.

    Connections that cross into a child are redirected to that child's node,
    so no dangling identifiers appear in the chart.
    """
    remap = {
        member: child.identifier
        for child in group.process_groups
        for member in _descendant_ids(child)
    }
    shallow = group.model_copy(
        update={
            "process_groups": [],
            "connections": [
                c.model_copy(
                    update={
                        "source": c.source.model_copy(
                            update={"id": remap.get(c.source.id, c.source.id)}
                        ),
                        "destination": c.destination.model_copy(
                            update={"id": remap.get(c.destination.id, c.destination.id)}
                        ),
                    }
                )
                for c in group.connections
            ],
        }
    )
    chart = to_mermaid(shallow, direction)
    nodes = [
        f'  {_node_id(child.identifier)}[["{_label(child.name)}"]]'
        for child in sorted(group.process_groups, key=lambda g: (g.name or "", g.identifier))
    ]
    if not nodes:
        return chart
    head, *tail = chart.split("\n")
    return "\n".join([head, *nodes, *tail])


def per_group(group: VersionedProcessGroup, direction: str = "LR") -> dict[str, str]:
    """One flowchart per process group, keyed by group name. Use for large flows."""
    charts = {group.name or group.identifier: to_mermaid_shallow(group, direction)}
    for child in group.process_groups:
        charts.update(per_group(child, direction))
    return charts
