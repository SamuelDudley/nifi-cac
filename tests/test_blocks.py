"""Block reuse and identifier stability."""

from nificac.blocks import s3_sink
from nificac.build import Group
from nificac.canonical import canonicalize


def _two_sinks():
    root = Group("demo", "Demo")
    kwargs = {"credentials": "svc", "region": "eu-west-2"}
    left = s3_sink(root, "OUT_Left", bucket="a", key="k", **kwargs)
    right = s3_sink(root, "OUT_Right", bucket="b", key="k", **kwargs)
    return root, left, right


def test_two_instances_have_distinct_identifiers():
    _, left, right = _two_sinks()
    assert left.identifier != right.identifier
    assert left.inputs["in"].identifier != right.inputs["in"].identifier


def test_two_instances_have_the_same_shape():
    root, left, right = _two_sinks()
    built = {g.name: g for g in root.build().process_groups}
    shape = lambda g: sorted(p.name for p in g.processors)
    assert shape(built["OUT_Left"]) == shape(built["OUT_Right"]) == ["OUT_PutS3Object"]


def test_identifiers_are_stable_across_runs():
    first = _two_sinks()[1].identifier
    second = _two_sinks()[1].identifier
    assert first == second


def test_connection_into_a_block_names_the_child_group():
    root = Group("demo", "Demo")
    upstream = root.processor("IN_Source", "T", __import__("nificac").AWS,
                              auto_terminate=[])
    sink = s3_sink(root, "OUT_Sink", bucket="b", key="k", credentials="svc", region="r")
    connection = root.connect(upstream, sink.inputs["in"], "success")
    assert connection.destination.type == "INPUT_PORT"
    assert connection.destination.group_id == sink.identifier
    assert connection.source.group_id == root.identifier


def test_renaming_a_block_only_moves_its_own_identifiers():
    root_a = Group("demo", "Demo")
    a = s3_sink(root_a, "OUT_Left", bucket="a", key="k", credentials="s", region="r")
    root_b = Group("demo", "Demo")
    b = s3_sink(root_b, "OUT_Renamed", bucket="a", key="k", credentials="s", region="r")
    assert a.identifier != b.identifier
    assert root_a.identifier == root_b.identifier
