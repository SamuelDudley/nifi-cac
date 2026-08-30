"""Repository rules."""

import pytest

from nificac import AWS, Group, PolicyError, assert_valid, check_all
from nificac.policy import check_names, check_routing, check_secrets


def test_example_flow_passes(snapshot):
    assert check_all(snapshot.flow_contents) == []


def test_literal_secret_is_rejected():
    root = Group("demo", "Demo")
    root.processor("IN_X", "T", AWS, {"Secret Access Key": "AKIAREAL"}, auto_terminate=["success"])
    errors = check_secrets(root.build())
    assert len(errors) == 1
    assert "Secret Access Key" in errors[0]


def test_parameter_reference_is_accepted():
    root = Group("demo", "Demo")
    root.processor("IN_X", "T", AWS, {"Secret Access Key": "#{aws.secret}"}, auto_terminate=["success"])
    assert check_secrets(root.build()) == []


def test_controller_service_reference_is_not_a_secret():
    root = Group("demo", "Demo")
    service = root.service("CS_Creds", "T", AWS)
    root.processor(
        "IN_X", "T", AWS,
        {"AWS Credentials Provider service": service.identifier},
        auto_terminate=["success"],
    )
    assert check_secrets(root.build()) == []


def test_missing_role_prefix_is_rejected():
    root = Group("demo", "Demo")
    root.processor("GetSomething", "T", AWS, auto_terminate=["success"])
    assert len(check_names(root.build())) == 1


def test_unhandled_relationship_is_rejected():
    root = Group("demo", "Demo")
    root.processor("IN_X", "T", AWS)
    errors = check_routing(root.build())
    assert any("auto-terminated" in e for e in errors)


def test_assert_valid_raises():
    root = Group("demo", "Demo")
    root.processor("GetSomething", "T", AWS)
    with pytest.raises(PolicyError):
        assert_valid(root.build())
