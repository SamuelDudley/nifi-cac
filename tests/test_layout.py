"""Sidecar geometry and the layering engine."""

import json
from pathlib import Path

from nificac import apply_layout, build_layout, extract_layout
from nificac.layout import rank
from nificac.models import RegisteredFlowSnapshot

FLOW_DIR = Path(__file__).resolve().parents[1] / "flows" / "telemetry"


def test_layout_is_deterministic(snapshot, build_telemetry):


    assert build_layout(snapshot.flow_contents) == build_layout(build_telemetry().flow_contents)


def test_layout_covers_every_component(snapshot):
    layout = build_layout(snapshot.flow_contents)
    for processor in snapshot.flow_contents.processors:
        assert processor.identifier in layout


def test_column_follows_graph_rank(snapshot):
    layout = build_layout(snapshot.flow_contents)
    by_name = {p.name: layout[p.identifier]["position"]["x"] for p in snapshot.flow_contents.processors}
    assert by_name["IN_GetSQS"] < by_name["PRC_ParseS3Event"] < by_name["PRC_FetchS3Object"]
    assert by_name["PRC_FetchS3Object"] < by_name["PRC_ExtractContent"] < by_name["PRC_InvokeLambda"]


def test_prefix_sets_colour_not_column(snapshot):
    layout = build_layout(snapshot.flow_contents)
    styles = {p.name: layout[p.identifier]["style"] for p in snapshot.flow_contents.processors}
    assert styles["IN_GetSQS"] == {"background-color": "#CCE5FF"}
    assert styles["PRC_ParseS3Event"] == {"background-color": "#E2E3E5"}


def test_geometry_round_trip(snapshot):
    layout = build_layout(snapshot.flow_contents)
    apply_layout(snapshot, layout)
    assert extract_layout(snapshot) == layout


def test_rank_is_cycle_safe():
    ranks = rank({"a", "b", "c"}, {("a", "b"), ("b", "c"), ("c", "a")})
    assert set(ranks) == {"a", "b", "c"}
    assert all(isinstance(v, int) for v in ranks.values())


def test_rank_uses_the_longest_path():
    ranks = rank({"a", "b", "c"}, {("a", "b"), ("b", "c"), ("a", "c")})
    assert ranks == {"a": 0, "b": 1, "c": 2}


def test_generated_flow_json_has_no_geometry():
    raw = json.loads((FLOW_DIR / "flow.json").read_text())
    assert "position" not in json.dumps(raw)
    parsed = RegisteredFlowSnapshot.model_validate(raw)
    assert all(p.position is None for p in parsed.flow_contents.processors)
