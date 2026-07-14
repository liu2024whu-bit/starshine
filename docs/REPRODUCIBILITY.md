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
