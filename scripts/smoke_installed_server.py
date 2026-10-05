from __future__ import annotations

from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app


def main() -> int:
    client = TestClient(create_app())

    health = client.get("/healthz")
    health.raise_for_status()
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["core_version"] == starshine_geo.__version__

    operators = client.get("/api/v1/operators")
    operators.raise_for_status()
    catalog = operators.json()
    assert catalog == starshine_geo.operator_catalog()

    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "clip",
                "inputs": {"input": "source", "mask": "mask"},
                "parameters": {},
                "output": "clipped",
            }
        ],
    }
    request = {"workflow": workflow, "layer_names": ["source", "mask"]}

    validation = client.post("/api/v1/workflows/validate", json=request)
    validation.raise_for_status()
    assert validation.json() == {"valid": True, "workflow_version": 1}

    plan = client.post("/api/v1/workflows/plan", json=request)
    plan.raise_for_status()
    assert plan.json()["required_external_layers"] == ["mask", "source"]
    assert plan.json()["terminal_layers"] == ["clipped"]

    print(
        "Installed Starshine Server smoke passed for "
        f"Starshine Geo {starshine_geo.__version__}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
