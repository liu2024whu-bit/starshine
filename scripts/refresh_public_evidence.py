from __future__ import annotations

import argparse
import json
from pathlib import Path

from starshine_geo import (
    build_workflow_contract,
    build_workflow_graph,
    build_workflow_preflight_sarif,
    explain_workflow,
    preflight_workflow_inputs,
    render_workflow_contract_markdown,
    render_workflow_explanation_markdown,
    render_workflow_mermaid,
    render_workflow_preflight_markdown,
)

ROOT = Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"
PLAN_WORKFLOW_PATH = EXAMPLES / "plan.workflow.json"
SOURCE_PATH = EXAMPLES / "data" / "clip-source.geojson"
MASK_PATH = EXAMPLES / "data" / "clip-mask.geojson"

_TRACKED_OUTPUTS = (
    EXAMPLES / "plan.workflow.contract.md",
    EXAMPLES / "plan.workflow.explanation.md",
    EXAMPLES / "plan.workflow.mmd",
    EXAMPLES / "plan.workflow.preflight.md",
    EXAMPLES / "plan.workflow.preflight.sarif",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _empty_collection() -> dict:
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [],
    }


def build_tracked_evidence() -> dict[Path, str]:
    workflow = _load(PLAN_WORKFLOW_PATH)
    declared_layers = {"source", "mask", "unused"}

    contract = build_workflow_contract(workflow, declared_layers)
    explanation = explain_workflow(workflow, declared_layers)
    graph = build_workflow_graph(workflow, declared_layers)

    source = _load(SOURCE_PATH)
    mask = _load(MASK_PATH)
    preflight = preflight_workflow_inputs(
        workflow,
        {"source": source, "mask": mask, "unused": _empty_collection()},
    )
    sarif_preflight = preflight_workflow_inputs(
        workflow,
        {"source": source, "mask": mask},
    )
    sarif = build_workflow_preflight_sarif(
        sarif_preflight,
        {
            "source": "examples/data/clip-source.geojson",
            "mask": "examples/data/clip-mask.geojson",
        },
        automation_id="starshine/preflight/examples/plan.workflow.json",
    )

    return {
        EXAMPLES / "plan.workflow.contract.md": render_workflow_contract_markdown(contract),
        EXAMPLES / "plan.workflow.explanation.md": render_workflow_explanation_markdown(
            explanation
        ),
        EXAMPLES / "plan.workflow.mmd": render_workflow_mermaid(graph),
        EXAMPLES / "plan.workflow.preflight.md": render_workflow_preflight_markdown(preflight),
        EXAMPLES / "plan.workflow.preflight.sarif": (
            json.dumps(sarif, ensure_ascii=False, indent=2) + "\n"
        ),
    }


def check(*, write: bool = False) -> None:
    generated = build_tracked_evidence()
    missing = set(_TRACKED_OUTPUTS) - set(generated)
    if missing:
        raise RuntimeError(
            "evidence generator omitted tracked outputs: "
            + ", ".join(str(path.relative_to(ROOT)) for path in sorted(missing))
        )

    stale: list[Path] = []
    for path in _TRACKED_OUTPUTS:
        expected = generated[path]
        if write:
            path.write_text(expected, encoding="utf-8")
            continue
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            stale.append(path)

    if stale:
        names = ", ".join(str(path.relative_to(ROOT)) for path in stale)
        raise RuntimeError(
            "tracked public evidence is stale: "
            f"{names}. Run 'python scripts/refresh_public_evidence.py --write'."
        )

    action = "refreshed" if write else "matches"
    print(f"Tracked public evidence {action} the current public contracts.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh or verify deterministic public workflow evidence"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite tracked example evidence instead of checking it",
    )
    args = parser.parse_args(argv)
    check(write=args.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
