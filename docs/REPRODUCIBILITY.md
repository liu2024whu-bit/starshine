# Reproducibility manifests

Starshine can optionally write a compact JSON manifest beside a selected workflow result. The
manifest is intended for classroom reproduction, research review, pull-request evidence, and
basic audit trails.

## Enable the manifest

Add `--manifest` to the normal `starshine run` command:

```bash
starshine run examples/workflow.json \
  --layer zones=examples/data/zones.geojson \
  --layer sites=examples/data/sites.geojson \
  --output-layer zone_summary \
  --output examples/output/zone_summary.geojson \
  --manifest examples/output/zone_summary.manifest.json
```

No manifest is written unless this option is supplied.

## Recorded fields

The version 1 manifest records:

- the Starshine package version and manifest version;
- a deterministic digest of the sanitized workflow;
- one content digest and declared `starshine:crs` value for each input layer;
- the ordered operations, layer references, sanitized parameters, and output names;
- the selected output layer name, content digest, and declared CRS.

The manifest deliberately does not copy feature content. Equivalent JSON objects produce the
same SHA-256 digest even when object-key order differs, while a content change produces a new
digest.

## Privacy and safety boundary

CLI file paths are never passed to the manifest builder. Absolute path strings, path-like
parameter fields, credential-bearing URLs, and parameters whose names indicate passwords,
tokens, API keys, secrets, DSNs, credentials, or private keys are redacted before workflow
hashing and step reporting.

A manifest is not a cryptographic signature, proof of authorship, or substitute for archiving
the referenced inputs. It is a deterministic description that helps reviewers detect changes
and reproduce a workflow with separately supplied data.


## Plan before execution, manifest after execution

A workflow plan and a reproducibility manifest answer different questions. `starshine plan` records
the validated dependency structure, resolved defaults, expected external layers, and declared CRS
behavior before data is loaded. `starshine run --manifest ...` records sanitized workflow and content
digests for the selected result after execution. Keeping both allows reviewers to compare intended
structure with produced evidence without placing feature content in either report.


## Verify a received result without rerunning

```bash
starshine verify-result examples/output/zone_summary.geojson \
  --manifest examples/output/zone_summary.manifest.json
```

The command is read-only and prints JSON to stdout. It compares the selected GeoJSON result's
canonical content digest and declared CRS with the supplied version 1 manifest. Exit codes are
`0` for a match, `1` for a mismatch, and `2` for unreadable or malformed inputs. Optional
`--diagnostic-format json` renders input errors on stderr as the standard CLI error envelope.
The public `verify_result_manifest(result, manifest)` API returns the same report:
`scope: "selected_output_only"`, `matched`, boolean `checks.content_digest` and
`checks.declared_crs`, and the expected/actual digests. It does not mutate either object.

JSON whitespace and object-key ordering do not affect matching. Array ordering and numeric JSON
representations retain the existing `digest_json` behavior: for example `1` and `1.0` in result
content can hash differently. CRS comparison uses the exact declared string, not semantic CRS
equivalence. Missing/empty result CRS follows the manifest builder's existing null convention.
The producer's package version need not equal the verifier's installed version.

**A match is selected-output consistency only.** The verifier does not authenticate either file,
check original inputs or the workflow, rerun operators, validate geometry, or establish spatial
accuracy. A result and manifest changed together can still match. It validates only the manifest
fields needed for these output checks, not the full provenance record. Keep the original inputs
and workflow separately for independent reproduction. GeoPackage conversion can change the
canonical JSON representation; supply the original GeoJSON result rather than expecting
byte-independent or spatial-equivalence verification of an exported dataset.
