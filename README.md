# nifi-cac

Configuration as Code for Apache NiFi 2.x. Flows are Python. Artifacts are
deterministic. Canvas geometry lives outside the reviewed file.

## Quick start

```sh
uv venv && uv pip install -e ".[dev]"
python -m nificac build      # generate artifacts for every flow
python -m nificac check      # fail if artifacts are stale or policy fails
python -m pytest             # 39 tests
```

## Repository layout

```
src/nificac/
  models.py      NiFi 2.x RegisteredFlowSnapshot schema
  build.py       Group builder, deterministic identifiers
  blocks.py      reusable flow blocks
  canonical.py   deterministic serialization and fingerprinting
  layout.py      geometry sidecar and the layering engine
  policy.py      repository rules
  mermaid.py     diagram generation
  cli.py         build / check / deploy
flows/telemetry/
  flow.py        source of truth, hand written
  flow.json      generated: canonical flow, no geometry
  layout.json    generated: geometry only
  flow.mmd       generated: Mermaid diagram
  flow.sha256    generated: fingerprint of flow.json
```

Only `flow.py` is edited. The other four files are generated and checked in, so
a pull request shows the config change, the geometry change, and the topology
change separately.

## Model rules

One model set covers parse and generate. There is no second normalized
hierarchy and no adapter.

| Choice | Effect |
|---|---|
| `alias_generator=to_camel` | No per-field `alias=`. `back_pressure_object_threshold` maps to `backPressureObjectThreshold`. |
| `extra="allow"` | Fields NiFi emits that are not declared survive parse and re-serialization. A missing model field costs typing, not data. |
| `populate_by_name=True` | Models accept either the Python name or the JSON alias. |

Two field markers drive everything downstream:

```python
instance_identifier: Optional[str] = Field(None, json_schema_extra=VOLATILE)
prioritizers: list[str] = Field(default_factory=list, json_schema_extra=ORDERED)
```

* `VOLATILE` — the field is stripped from `flow.json`. Use it for anything that
  changes between instances or exports without changing behaviour.
* `ORDERED` — the list order is semantic, so it is never sorted.

Adding a NiFi field is one line in `models.py`. No other module changes.

## Determinism

`canonical_json` produces the same bytes for two flows that behave the same.

1. Volatile fields are dropped: `instanceIdentifier`, `position`, `bends`,
   `style`, `labelIndex`, `zIndex`, label geometry, `propertyDescriptors`.
2. Every list is sorted by `identifier`, then `name`, then `type`, unless it is
   marked `ORDERED`.
3. Every map is sorted by key.
4. Model fields that are `None` or empty are omitted. A `None` *inside* a map is
   kept, because `{"Password": null}` means "set but sensitive" and is not the
   same as an absent key.
5. Default values are kept, so a NiFi default change cannot silently alter
   behaviour.

Identifiers come from `uuid5(NAMESPACE, path)` where `path` is the component's
position in the group tree:

```
telemetry/OUT_Results/OUT_PutS3Object      7f123fac-8666-50ea-a4e1-8a1fa0b1bf61
telemetry/ERR_DeadLetter/OUT_PutS3Object   54876ef0-a8df-548c-9555-f1b00c000619
```

Rerunning `build` gives the same identifiers. Two instances of one block get
different identifiers. Set `NAMESPACE` once per organisation.

## Blocks

A block is a function that builds a child process group with named ports.

```python
def s3_sink(parent, name, *, bucket, key, credentials, region) -> Group:
    """Write flow file content to S3.

    Ports:
      in       (input)  flow files to write
      failure  (output) flow files S3 rejected
    """
```

Call it twice and you get two independent instances from one definition:

```python
results = s3_sink(root, "OUT_Results", bucket="#{s3.output.bucket}",
                  key="enriched/${filename}", credentials=creds.identifier, region=REGION)
dead    = s3_sink(root, "ERR_DeadLetter", bucket="#{s3.deadletter.bucket}",
                  key="failed/${uuid}", credentials=creds.identifier, region=REGION)

root.connect(invoke, results.inputs["in"], "success")
root.connect(errors, dead.inputs["in"])
```

`connect` reads `group_id` off the component, so a connection into a child
block's input port names the child group with no extra bookkeeping.

Block contract:

* take a parent `Group` and an instance name
* return the child `Group`
* expose ports through `group.inputs[...]` and `group.outputs[...]`
* list every port in the docstring

## Layout

`flow.json` holds no coordinates. `layout.json` holds nothing else.

Column comes from graph rank (longest path, cycle safe). Row order comes from
`(rank, name, identifier)`, never from export order. The name prefix sets colour
only.

| Prefix | Colour | Role |
|---|---|---|
| `IN_` | `#CCE5FF` | ingest |
| `PRC_` | `#E2E3E5` | processing |
| `SUB_` | `#E2D9F3` | hand-off to a sub-flow |
| `OUT_` | `#D4EDDA` | sink |
| `ERR_` | `#F8D7DA` | error handling |

Deploying is parse, `apply_layout`, POST:

```sh
python -m nificac deploy flows/telemetry > deployable.json
```

## Policy

`nificac check` is the CI gate. Three rules run against every flow:

| Check | Rule |
|---|---|
| `check_secrets` | A sensitive property is `null` or a `#{parameter}` reference. Uses `propertyDescriptors` when present, property name matching otherwise. Controller service references are exempt. |
| `check_names` | Every processor and controller service name starts with a role prefix. |
| `check_routing` | Every processor has an outbound route or auto-terminated relationships, and an inbound connection unless it is `IN_`. |

Add a rule by appending a function to `policy.CHECKS`.

`flow.py` is compiled by `cli.load`, not imported. CPython validates a cached
`.pyc` on source mtime and size at one second resolution, so a branch switch can
leave a stale cache that would generate artifacts from source no longer on disk.

## Diagrams

`flow.mmd` is regenerated on every build and rendered inline by GitHub. Blocks
become `subgraph` boxes. Edge labels are the selected relationships. The sort
keys match `canonical.py`, so the diagram diffs as cleanly as the flow.

```sh
python -c "from nificac import to_mermaid, RegisteredFlowSnapshot as S; \
  print(to_mermaid(S.model_validate_json(open('flows/telemetry/flow.json').read()).flow_contents))"
```

Limits:

* Mermaid layout degrades past roughly 50 nodes. Use `per_group()` for large
  flows and link the diagrams.
* Node placement is not controllable and will not match the NiFi canvas.
* Properties do not fit. The diagram renders topology only.

## Example flow

`flows/telemetry` waits on an SQS queue, fetches the S3 object named in the
event, extracts the payload, posts it to Lambda, and writes the response to S3.
Every failure relationship fans into one funnel and lands in a dead letter
bucket.

See [flows/telemetry/README.md](flows/telemetry/README.md) for the diagram.

## Verified against NiFi

The schema follows the NiFi 2.0 flow definition format and the processor
property names in the NiFi 2.0 documentation. It has not been imported into a
running NiFi instance. Before first deploy, export one flow from your instance
and run:

```sh
python -c "from nificac import RegisteredFlowSnapshot as S; \
  s = S.model_validate_json(open('exported.json').read()); \
  print(sorted((s.flow_contents.model_extra or {}).keys()))"
```

That prints every field NiFi sent that `models.py` does not declare yet.
`extra="allow"` means an undeclared field still round-trips; declaring it only
adds type checking.
