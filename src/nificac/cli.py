"""Command line entry point.

  nificac build [FLOW_DIR ...]   generate artifacts
  nificac check [FLOW_DIR ...]   fail if artifacts are stale or policy fails
  nificac deploy FLOW_DIR        print the deployable flow (layout re-applied)

A flow directory holds ``flow.py`` exposing ``build() -> RegisteredFlowSnapshot``.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from typing import Iterable

from .canonical import canonical_json, fingerprint
from .layout import apply_layout, build_layout
from .mermaid import to_mermaid
from .models import RegisteredFlowSnapshot
from .policy import check_all

FLOWS_ROOT = Path("flows")
ARTIFACTS = ("flow.json", "layout.json", "flow.mmd", "flow.sha256")


def discover(paths: Iterable[str]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    return sorted(p.parent for p in FLOWS_ROOT.glob("*/flow.py"))


def load(flow_dir: Path) -> RegisteredFlowSnapshot:
    """Execute ``flow.py`` and return its snapshot.

    The source is compiled here rather than imported. CPython validates a
    cached ``.pyc`` on source mtime and size at one second resolution, so a
    branch switch or ``git checkout`` can leave a stale cache that generates
    artifacts from source that is no longer on disk.
    """
    source = flow_dir / "flow.py"
    if not source.exists():
        raise SystemExit(f"{source} does not exist")
    module = types.ModuleType(f"flow_{flow_dir.name}")
    module.__file__ = str(source)
    sys.path.insert(0, str(flow_dir))
    try:
        exec(compile(source.read_text(), str(source), "exec"), module.__dict__)
    finally:
        sys.path.remove(str(flow_dir))
    return module.build()


def render(snapshot: RegisteredFlowSnapshot) -> dict[str, str]:
    return {
        "flow.json": canonical_json(snapshot),
        "layout.json": json.dumps(build_layout(snapshot.flow_contents), indent=2, sort_keys=True)
        + "\n",
        "flow.mmd": to_mermaid(snapshot.flow_contents),
        "flow.sha256": fingerprint(snapshot) + "\n",
    }


def cmd_build(flow_dirs: list[Path], strict: bool) -> int:
    failures = 0
    for flow_dir in flow_dirs:
        snapshot = load(flow_dir)
        errors = check_all(snapshot.flow_contents)
        for error in errors:
            print(f"{flow_dir}: {error}", file=sys.stderr)
        if errors and strict:
            failures += 1
            continue
        for name, content in render(snapshot).items():
            (flow_dir / name).write_text(content)
        print(f"{flow_dir}: wrote {', '.join(ARTIFACTS)}")
    return 1 if failures else 0


def cmd_check(flow_dirs: list[Path]) -> int:
    failures = 0
    for flow_dir in flow_dirs:
        snapshot = load(flow_dir)
        for error in check_all(snapshot.flow_contents):
            print(f"{flow_dir}: {error}", file=sys.stderr)
            failures += 1
        for name, content in render(snapshot).items():
            target = flow_dir / name
            if not target.exists():
                print(f"{flow_dir}: {name} is missing", file=sys.stderr)
                failures += 1
            elif target.read_text() != content:
                print(f"{flow_dir}: {name} is stale, run 'nificac build'", file=sys.stderr)
                failures += 1
        if not failures:
            print(f"{flow_dir}: ok")
    return 1 if failures else 0


def cmd_deploy(flow_dir: Path) -> int:
    snapshot = RegisteredFlowSnapshot.model_validate_json((flow_dir / "flow.json").read_text())
    apply_layout(snapshot, json.loads((flow_dir / "layout.json").read_text()))
    print(snapshot.model_dump_json(by_alias=True, exclude_none=True, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nificac")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="generate artifacts")
    build.add_argument("flow_dir", nargs="*")
    build.add_argument("--strict", action="store_true", help="do not write when policy fails")

    check = sub.add_parser("check", help="fail if artifacts are stale or policy fails")
    check.add_argument("flow_dir", nargs="*")

    deploy = sub.add_parser("deploy", help="print the deployable flow")
    deploy.add_argument("flow_dir")

    args = parser.parse_args(argv)
    if args.command == "build":
        return cmd_build(discover(args.flow_dir), args.strict)
    if args.command == "check":
        return cmd_check(discover(args.flow_dir))
    return cmd_deploy(Path(args.flow_dir))


if __name__ == "__main__":
    raise SystemExit(main())
