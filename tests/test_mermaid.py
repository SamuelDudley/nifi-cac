"""Diagram generation."""

from nificac import per_group, to_mermaid
from nificac.mermaid import to_mermaid_shallow


def test_diagram_is_deterministic(snapshot, build_telemetry):


    assert to_mermaid(snapshot.flow_contents) == to_mermaid(build_telemetry().flow_contents)


def test_every_block_becomes_a_subgraph(snapshot):
    chart = to_mermaid(snapshot.flow_contents)
    for child in snapshot.flow_contents.process_groups:
        assert f'["{child.name}"]' in chart
    assert chart.count("subgraph") == len(snapshot.flow_contents.process_groups)


def test_relationships_label_the_edges(snapshot):
    chart = to_mermaid(snapshot.flow_contents)
    assert '-- "success" -->' in chart
    assert '-- "matched" -->' in chart
    assert '-- "failure" -->' in chart


def test_shallow_diagram_has_no_dangling_identifiers(snapshot):
    chart = to_mermaid_shallow(snapshot.flow_contents)
    declared = {
        line.strip().split("[")[0].split("(")[0]
        for line in chart.splitlines()
        if line.strip().startswith("n") and ("[" in line or "((" in line)
    }
    for line in chart.splitlines():
        if "-->" not in line:
            continue
        left, right = line.split("-->")
        assert left.split()[0] in declared
        assert right.strip() in declared


def test_per_group_returns_one_chart_per_group(snapshot):
    charts = per_group(snapshot.flow_contents)
    assert len(charts) == 1 + len(snapshot.flow_contents.process_groups)
    assert "Telemetry Enrichment" in charts
