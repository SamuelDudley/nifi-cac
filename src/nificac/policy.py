"""Checks that run before an artifact is written."""

from __future__ import annotations

import re

from .models import VersionedProcessGroup

#: Property names that must never hold a literal value.
SENSITIVE_NAME = re.compile(
    r"secret|password|passwd|token|credential|private[ _-]?key|access[ _-]?key",
    re.IGNORECASE,
)
PARAMETER_REFERENCE = re.compile(r"^#\{[^}]+\}$")
#: A property holding a controller service reference contains its identifier.
SERVICE_REFERENCE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

VALID_PREFIXES = ("IN_", "PRC_", "SUB_", "OUT_", "ERR_", "CS_")


class PolicyError(ValueError):
    """A flow violated a repository rule."""


def _is_secret(name: str, descriptor, value: str | None) -> bool:
    if value is None or PARAMETER_REFERENCE.match(value):
        return False
    if descriptor is not None and descriptor.identifies_controller_service:
        return False
    if SERVICE_REFERENCE.match(value):
        return False
    return bool(descriptor and descriptor.sensitive) or bool(SENSITIVE_NAME.search(name))


def check_secrets(group: VersionedProcessGroup, path: str = "") -> list[str]:
    """Every sensitive property must be null or a parameter reference.

    ``propertyDescriptors`` are used when present. Generated flows have none,
    so property names are matched against :data:`SENSITIVE_NAME` as well.
    """
    errors: list[str] = []
    where = f"{path}/{group.name}" if path else (group.name or group.identifier)
    for component in (*group.processors, *group.controller_services):
        for name, value in sorted(component.properties.items()):
            descriptor = component.property_descriptors.get(name)
            if _is_secret(name, descriptor, value):
                errors.append(f"{where}/{component.name}: property '{name}' holds a literal value")
    for child in group.process_groups:
        errors.extend(check_secrets(child, where))
    return errors


def check_names(group: VersionedProcessGroup, path: str = "") -> list[str]:
    """Component names carry a role prefix so the layout engine can colour them."""
    errors: list[str] = []
    where = f"{path}/{group.name}" if path else (group.name or group.identifier)
    for component in (*group.processors, *group.controller_services):
        if not (component.name or "").startswith(VALID_PREFIXES):
            errors.append(
                f"{where}/{component.name}: name lacks a role prefix "
                f"({', '.join(VALID_PREFIXES)})"
            )
    for child in group.process_groups:
        errors.extend(check_names(child, where))
    return errors


def check_routing(group: VersionedProcessGroup, path: str = "") -> list[str]:
    """Every processor relationship is either connected or auto-terminated.

    An unhandled relationship stops the processor from starting in NiFi.
    """
    errors: list[str] = []
    where = f"{path}/{group.name}" if path else (group.name or group.identifier)
    sources = {c.source.id for c in group.connections}
    destinations = {c.destination.id for c in group.connections}
    for processor in group.processors:
        connected = processor.identifier in sources
        terminated = bool(processor.auto_terminated_relationships)
        if not connected and not terminated:
            errors.append(f"{where}/{processor.name}: no outbound route and nothing auto-terminated")
        if processor.identifier not in destinations and not (processor.name or "").startswith("IN_"):
            errors.append(f"{where}/{processor.name}: no inbound connection")
    for child in group.process_groups:
        errors.extend(check_routing(child, where))
    return errors


CHECKS = (check_secrets, check_names, check_routing)


def check_all(group: VersionedProcessGroup) -> list[str]:
    return [error for check in CHECKS for error in check(group)]


def assert_valid(group: VersionedProcessGroup) -> None:
    errors = check_all(group)
    if errors:
        raise PolicyError("\n".join(errors))
