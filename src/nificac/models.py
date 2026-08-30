"""Pydantic models for the NiFi 2.x flow definition format (RegisteredFlowSnapshot).

Field markers
-------------
VOLATILE  Field is stripped by :mod:`nificac.canonical`. Use for anything that
          changes between instances or exports without changing behaviour.
ORDERED   List order is semantic. :mod:`nificac.canonical` must not sort it.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

VOLATILE: dict[str, Any] = {"volatile": True}
ORDERED: dict[str, Any] = {"ordered": True}


class NiFiModel(BaseModel):
    """Base for every model.

    ``extra="allow"`` is the round-trip guarantee: fields NiFi emits that are
    not declared here survive parse and re-serialization instead of being
    dropped. ``alias_generator`` removes the need for per-field ``alias=``.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class Position(NiFiModel):
    x: float
    y: float


class Bundle(NiFiModel):
    group: str
    artifact: str
    version: str


class PropertyDescriptor(NiFiModel):
    name: str
    display_name: Optional[str] = None
    identifies_controller_service: bool = False
    sensitive: bool = False


class ConnectableComponent(NiFiModel):
    id: str
    type: Literal[
        "PROCESSOR",
        "INPUT_PORT",
        "OUTPUT_PORT",
        "REMOTE_INPUT_PORT",
        "REMOTE_OUTPUT_PORT",
        "FUNNEL",
    ]
    group_id: str
    name: Optional[str] = None
    comments: Optional[str] = None
    instance_identifier: Optional[str] = Field(None, json_schema_extra=VOLATILE)


# --- mixins ------------------------------------------------------------------


class Component(NiFiModel):
    """Identity fields shared by every versioned component."""

    identifier: str
    name: Optional[str] = None
    comments: Optional[str] = None
    component_type: Optional[str] = None
    group_identifier: Optional[str] = None
    #: Per-instance UUID. Differs on every NiFi instance, so it is volatile.
    instance_identifier: Optional[str] = Field(None, json_schema_extra=VOLATILE)


class Positioned(NiFiModel):
    position: Optional[Position] = Field(None, json_schema_extra=VOLATILE)


class Configurable(NiFiModel):
    """Anything with a bundle and a property map."""

    type: str
    bundle: Bundle
    properties: dict[str, Optional[str]] = Field(default_factory=dict)
    #: Derived from the NAR, not from user configuration. Retained at parse
    #: time so :mod:`nificac.policy` can find sensitive properties; stripped
    #: from the canonical artifact.
    property_descriptors: dict[str, PropertyDescriptor] = Field(
        default_factory=dict, json_schema_extra=VOLATILE
    )


# --- components --------------------------------------------------------------


class VersionedProcessor(Component, Positioned, Configurable):
    scheduling_strategy: str = "TIMER_DRIVEN"
    scheduling_period: str = "0 sec"
    execution_node: str = "ALL"
    penalty_duration: str = "30 sec"
    yield_duration: str = "1 sec"
    bulletin_level: str = "WARN"
    run_duration_millis: int = 0
    concurrently_schedulable_task_count: int = 1
    auto_terminated_relationships: list[str] = Field(default_factory=list)
    scheduled_state: str = "ENABLED"
    retry_count: int = 10
    retried_relationships: list[str] = Field(default_factory=list)
    backoff_mechanism: str = "PENALIZE_FLOWFILE"
    max_backoff_period: str = "10 mins"
    style: dict[str, str] = Field(default_factory=dict, json_schema_extra=VOLATILE)


class VersionedControllerService(Component, Configurable):
    scheduled_state: str = "ENABLED"
    bulletin_level: str = "WARN"
    controller_service_apis: list[dict[str, Any]] = Field(default_factory=list)


class VersionedConnection(Component):
    source: ConnectableComponent
    destination: ConnectableComponent
    selected_relationships: list[str] = Field(default_factory=list)
    back_pressure_object_threshold: int = 10000
    back_pressure_data_size_threshold: str = "1 GB"
    flow_file_expiration: str = "0 sec"
    load_balance_strategy: str = "DO_NOT_LOAD_BALANCE"
    partitioning_attribute: Optional[str] = None
    load_balance_compression: str = "DO_NOT_COMPRESS"
    #: Prioritizer order decides dequeue order. Sorting it changes behaviour.
    prioritizers: list[str] = Field(default_factory=list, json_schema_extra=ORDERED)
    bends: list[Position] = Field(default_factory=list, json_schema_extra=VOLATILE)
    label_index: int = Field(0, json_schema_extra=VOLATILE)
    z_index: int = Field(0, json_schema_extra=VOLATILE)


class VersionedPort(Component, Positioned):
    type: Literal["INPUT_PORT", "OUTPUT_PORT"]
    concurrently_schedulable_task_count: int = 1
    scheduled_state: str = "ENABLED"
    allow_remote_access: bool = False
    port_function: str = "STANDARD"


class VersionedFunnel(Component, Positioned):
    pass


class VersionedLabel(Component, Positioned):
    label: str = ""
    width: float = Field(0.0, json_schema_extra=VOLATILE)
    height: float = Field(0.0, json_schema_extra=VOLATILE)
    style: dict[str, str] = Field(default_factory=dict, json_schema_extra=VOLATILE)
    z_index: int = Field(0, json_schema_extra=VOLATILE)


class VersionedProcessGroup(Component, Positioned):
    process_groups: list["VersionedProcessGroup"] = Field(default_factory=list)
    processors: list[VersionedProcessor] = Field(default_factory=list)
    connections: list[VersionedConnection] = Field(default_factory=list)
    controller_services: list[VersionedControllerService] = Field(default_factory=list)
    input_ports: list[VersionedPort] = Field(default_factory=list)
    output_ports: list[VersionedPort] = Field(default_factory=list)
    funnels: list[VersionedFunnel] = Field(default_factory=list)
    labels: list[VersionedLabel] = Field(default_factory=list)
    remote_process_groups: list[dict[str, Any]] = Field(default_factory=list)
    parameter_context_name: Optional[str] = None
    default_flow_file_expiration: Optional[str] = None
    default_back_pressure_object_threshold: Optional[int] = None
    default_back_pressure_data_size_threshold: Optional[str] = None
    flow_file_concurrency: Optional[str] = None
    flow_file_outbound_policy: Optional[str] = None
    execution_engine: Optional[str] = None
    max_concurrent_tasks: Optional[int] = None
    stateless_flow_timeout: Optional[str] = None
    scheduled_state: Optional[str] = None


class VersionedParameter(NiFiModel):
    name: str
    description: Optional[str] = None
    sensitive: bool = False
    value: Optional[str] = None
    provided: bool = False


class VersionedParameterContext(Component):
    parameters: list[VersionedParameter] = Field(default_factory=list)
    #: Inheritance order decides which context wins a name collision.
    inherited_parameter_contexts: list[str] = Field(
        default_factory=list, json_schema_extra=ORDERED
    )
    description: Optional[str] = None


class RegisteredFlowSnapshot(NiFiModel):
    """Top level of a NiFi 2.x "Download flow definition" file."""

    flow_contents: VersionedProcessGroup
    flow_encoding_version: str = "1.0"
    parameter_contexts: dict[str, VersionedParameterContext] = Field(default_factory=dict)
    external_controller_services: dict[str, Any] = Field(default_factory=dict)
    parameter_providers: dict[str, Any] = Field(default_factory=dict)


VersionedProcessGroup.model_rebuild()
