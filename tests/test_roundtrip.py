"""Parse, re-serialize, redeploy."""

import json
from pathlib import Path

from nificac import apply_layout, canonical_json, fingerprint
from nificac.models import RegisteredFlowSnapshot

FLOW_DIR = Path(__file__).resolve().parents[1] / "flows" / "telemetry"


def test_artifacts_match_the_source(snapshot):
    assert (FLOW_DIR / "flow.json").read_text() == canonical_json(snapshot)
    assert (FLOW_DIR / "flow.sha256").read_text().strip() == fingerprint(snapshot)


def test_parse_then_canonicalize_is_a_fixed_point():
    text = (FLOW_DIR / "flow.json").read_text()
    assert canonical_json(RegisteredFlowSnapshot.model_validate_json(text)) == text


def test_deploy_restores_every_position():
    snapshot = RegisteredFlowSnapshot.model_validate_json((FLOW_DIR / "flow.json").read_text())
    layout = json.loads((FLOW_DIR / "layout.json").read_text())
    assert all(p.position is None for p in snapshot.flow_contents.processors)
    apply_layout(snapshot, layout)
    assert all(p.position is not None for p in snapshot.flow_contents.processors)


def test_block_instances_stay_distinct_after_parsing():
    snapshot = RegisteredFlowSnapshot.model_validate_json((FLOW_DIR / "flow.json").read_text())
    sinks = [g for g in snapshot.flow_contents.process_groups if "OUT_PutS3Object" in
             [p.name for p in g.processors]]
    assert len(sinks) == 2
    assert sinks[0].processors[0].identifier != sinks[1].processors[0].identifier


def test_load_ignores_stale_bytecode(tmp_path):
    """A cached .pyc must never win over the source file.

    CPython validates a cached .pyc on source mtime and size at one second
    resolution. A branch switch can produce a same-size, same-second source
    that the cache wrongly satisfies.
    """
    import os
    import py_compile

    from nificac.cli import load

    flow_dir = tmp_path / "demo"
    flow_dir.mkdir()
    source = flow_dir / "flow.py"
    template = (
        "from nificac.build import AWS, Group\n"
        "from nificac.models import RegisteredFlowSnapshot\n"
        "def build():\n"
        "    root = Group('demo', 'Demo')\n"
        "    root.processor('IN_X', 'T', AWS, {{'Batch Size': '{size}'}},\n"
        "                   auto_terminate=['success'])\n"
        "    return RegisteredFlowSnapshot(flow_contents=root.build())\n"
    )

    source.write_text(template.format(size="10"))
    py_compile.compile(str(source), doraise=True)
    stamp = source.stat().st_mtime

    # Same length, same mtime: exactly what a branch switch can produce.
    source.write_text(template.format(size="25"))
    os.utime(source, (stamp, stamp))

    snapshot = load(flow_dir)
    assert snapshot.flow_contents.processors[0].properties["Batch Size"] == "25"
