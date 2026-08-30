"""Determinism and volatile field stripping."""

import json

from nificac import canonical_json, canonicalize, fingerprint
from nificac.build import AWS, Group
from nificac.models import (
    Bundle,
    ConnectableComponent,
    Position,
    PropertyDescriptor,
    VersionedConnection,
    VersionedProcessor,
)

VOLATILE_KEYS = {"position", "instanceIdentifier", "bends", "style", "propertyDescriptors",
                 "labelIndex", "zIndex", "width", "height"}


def _keys(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        found |= set(node)
        for value in node.values():
            _keys(value, found)
    elif isinstance(node, list):
        for item in node:
            _keys(item, found)
    return found


def test_build_is_deterministic(snapshot, build_telemetry):


    assert canonical_json(snapshot) == canonical_json(build_telemetry())
    assert fingerprint(snapshot) == fingerprint(build_telemetry())


def test_no_volatile_keys_in_canonical_output(snapshot):
    assert _keys(canonicalize(snapshot)) & VOLATILE_KEYS == set()


def test_geometry_does_not_change_the_fingerprint(snapshot):
    before = fingerprint(snapshot)
    snapshot.flow_contents.processors[0].position = Position(x=999.0, y=999.0)
    snapshot.flow_contents.processors[0].instance_identifier = "some-instance-uuid"
    snapshot.flow_contents.processors[0].style = {"background-color": "#000000"}
    assert fingerprint(snapshot) == before


def test_configuration_does_change_the_fingerprint(snapshot):
    before = fingerprint(snapshot)
    snapshot.flow_contents.processors[0].properties["Batch Size"] = "25"
    assert fingerprint(snapshot) != before


def test_export_order_does_not_matter(snapshot):
    before = canonical_json(snapshot)
    snapshot.flow_contents.processors.reverse()
    snapshot.flow_contents.connections.reverse()
    snapshot.flow_contents.process_groups.reverse()
    assert canonical_json(snapshot) == before


def test_null_property_value_survives():
    processor = VersionedProcessor(
        identifier="a", name="IN_X", type="T", bundle=AWS,
        properties={"Password": None, "Bucket": "b"},
    )
    assert canonicalize(processor)["properties"] == {"Bucket": "b", "Password": None}


def test_ordered_lists_keep_their_order():
    endpoint = ConnectableComponent(id="s", type="PROCESSOR", group_id="g")
    connection = VersionedConnection(
        identifier="c", source=endpoint, destination=endpoint,
        prioritizers=["ZZZ.Prioritizer", "AAA.Prioritizer"],
        selected_relationships=["success", "failure"],
    )
    result = canonicalize(connection)
    assert result["prioritizers"] == ["ZZZ.Prioritizer", "AAA.Prioritizer"]
    assert result["selectedRelationships"] == ["failure", "success"]


def test_unknown_nifi_fields_survive_the_round_trip():
    raw = {
        "identifier": "a", "name": "IN_X", "type": "T",
        "bundle": {"group": "g", "artifact": "a", "version": "1"},
        "someFutureNiFiField": {"nested": [3, 1, 2]},
    }
    processor = VersionedProcessor.model_validate(raw)
    assert canonicalize(processor)["someFutureNiFiField"] == {"nested": [1, 2, 3]}


def test_property_descriptors_are_stripped_but_readable():
    processor = VersionedProcessor(
        identifier="a", name="IN_X", type="T", bundle=AWS,
        property_descriptors={"Password": PropertyDescriptor(name="Password", sensitive=True)},
    )
    assert processor.property_descriptors["Password"].sensitive is True
    assert "propertyDescriptors" not in canonicalize(processor)
