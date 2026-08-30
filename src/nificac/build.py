"""Flow construction.

Every identifier is ``uuid5(NAMESPACE, path)``. The path is the component's
position in the group tree, so identifiers are stable across runs and distinct
between two instances of the same block.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional, Union

from .models import (
    Bundle,
    ConnectableComponent,
    VersionedConnection,
    VersionedControllerService,
    VersionedFunnel,
    VersionedLabel,
    VersionedPort,
    VersionedProcessGroup,
    VersionedProcessor,
)

#: Change this and every identifier changes. Pick one per organisation.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/nifi-cac")

AWS = Bundle(group="org.apache.nifi", artifact="nifi-aws-nar", version="2.0.0")
STANDARD = Bundle(group="org.apache.nifi", artifact="nifi-standard-nar", version="2.0.0")

Connectable = Union[VersionedProcessor, VersionedPort, VersionedFunnel]


def sid(path: str) -> str:
    """Deterministic component identifier for a slash-separated path."""
    return str(uuid.uuid5(NAMESPACE, path))


def _endpoint(component: Connectable) -> ConnectableComponent:
    """Build a connection endpoint.

    ``group_id`` is read off the component, so a connection into a child
    block's input port names the child group with no extra bookkeeping.
    """
    if isinstance(component, VersionedPort):
        kind = component.type
    elif isinstance(component, VersionedFunnel):
        kind = "FUNNEL"
    else:
        kind = "PROCESSOR"
    return ConnectableComponent(
        id=component.identifier,
        type=kind,
        group_id=component.group_identifier or "",
        name=component.name,
    )


class Group:
    """Builder for one :class:`VersionedProcessGroup`."""

    def __init__(self, path: str, name: str, parent: Optional["Group"] = None) -> None:
        self.path = path
        self.name = name
        self.identifier = sid(path)
        self.parent = parent
        self.inputs: dict[str, VersionedPort] = {}
        self.outputs: dict[str, VersionedPort] = {}
        self._processors: list[VersionedProcessor] = []
        self._connections: list[VersionedConnection] = []
        self._services: list[VersionedControllerService] = []
        self._funnels: list[VersionedFunnel] = []
        self._labels: list[VersionedLabel] = []
        self._children: list["Group"] = []

    # --- components ---------------------------------------------------------

    def processor(
        self,
        name: str,
        type_: str,
        bundle: Bundle,
        properties: Optional[dict[str, Optional[str]]] = None,
        auto_terminate: Iterable[str] = (),
        **kwargs: Any,
    ) -> VersionedProcessor:
        component = VersionedProcessor(
            identifier=sid(f"{self.path}/{name}"),
            name=name,
            type=type_,
            bundle=bundle,
            component_type="PROCESSOR",
            group_identifier=self.identifier,
            properties=properties or {},
            auto_terminated_relationships=sorted(auto_terminate),
            **kwargs,
        )
        self._processors.append(component)
        return component

    def service(
        self,
        name: str,
        type_: str,
        bundle: Bundle,
        properties: Optional[dict[str, Optional[str]]] = None,
    ) -> VersionedControllerService:
        component = VersionedControllerService(
            identifier=sid(f"{self.path}/{name}"),
            name=name,
            type=type_,
            bundle=bundle,
            component_type="CONTROLLER_SERVICE",
            group_identifier=self.identifier,
            properties=properties or {},
        )
        self._services.append(component)
        return component

    def funnel(self, name: str) -> VersionedFunnel:
        component = VersionedFunnel(
            identifier=sid(f"{self.path}/{name}"),
            name=name,
            component_type="FUNNEL",
            group_identifier=self.identifier,
        )
        self._funnels.append(component)
        return component

    def port(self, name: str, direction: str) -> VersionedPort:
        """Declare a block boundary port. ``direction`` is INPUT_PORT or OUTPUT_PORT."""
        component = VersionedPort(
            identifier=sid(f"{self.path}/{direction.lower()}/{name}"),
            name=name,
            type=direction,
            component_type=direction,
            group_identifier=self.identifier,
        )
        (self.inputs if direction == "INPUT_PORT" else self.outputs)[name] = component
        return component

    def block(self, name: str) -> "Group":
        """Create a child group. Its path prefix makes its identifiers unique."""
        child = Group(f"{self.path}/{name}", name, parent=self)
        self._children.append(child)
        return child

    # --- wiring -------------------------------------------------------------

    def connect(
        self, source: Connectable, destination: Connectable, *relationships: str
    ) -> VersionedConnection:
        """Connect two components. Omit relationships for ports and funnels."""
        selected = sorted(relationships) or [""]
        component = VersionedConnection(
            identifier=sid(
                f"{self.path}/connection/{source.identifier}/{destination.identifier}"
                f"/{'+'.join(selected)}"
            ),
            name="",
            component_type="CONNECTION",
            group_identifier=self.identifier,
            source=_endpoint(source),
            destination=_endpoint(destination),
            selected_relationships=selected,
        )
        self._connections.append(component)
        return component

    def build(self) -> VersionedProcessGroup:
        return VersionedProcessGroup(
            identifier=self.identifier,
            name=self.name,
            component_type="PROCESS_GROUP",
            group_identifier=self.parent.identifier if self.parent else None,
            processors=self._processors,
            connections=self._connections,
            controller_services=self._services,
            funnels=self._funnels,
            labels=self._labels,
            input_ports=list(self.inputs.values()),
            output_ports=list(self.outputs.values()),
            process_groups=[child.build() for child in self._children],
        )
