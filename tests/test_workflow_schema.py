import json
from pathlib import Path


SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "workflow-v1.schema.json"


def test_workflow_schema_is_machine_readable_and_versioned():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["version"]["const"] == 1
    assert schema["properties"]["steps"]["minItems"] == 1
    assert schema["$defs"]["step"]["required"] == ["operation", "inputs", "output"]


def test_workflow_schema_lists_only_registered_public_operations():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$defs"]["step"]["properties"]["operation"]["enum"] == [
        "buffer",
        "dissolve",
        "summarize_points_within",
    ]
