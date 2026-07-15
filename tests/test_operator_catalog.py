import json
from pathlib import Path

from jsonschema import Draft202012Validator

from starshine_geo import OPERATOR_REGISTRY, operator_catalog
from starshine_geo.cli import main
from starshine_geo.workflow import OPERATORS, OPERATOR_INPUTS, OPERATOR_PARAMETER_SPECS

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SCHEMA_PATH = ROOT / "schemas" / "operator-catalog-v1.schema.json"
WORKFLOW_SCHEMA_PATH = ROOT / "schemas" / "workflow-v1.schema.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_contracts() -> tuple[dict, dict[str, dict]]:
    schema = _load(WORKFLOW_SCHEMA_PATH)
    contracts = {}
    for reference in schema["properties"]["steps"]["items"]["oneOf"]:
        definition = schema["$defs"][reference["$ref"].rsplit("/", 1)[-1]]
        contracts[definition["properties"]["operation"]["const"]] = definition
    return schema, contracts


def _resolve_local_refs(value, root):
    if isinstance(value, dict):
        if set(value) == {"$ref"} and value["$ref"].startswith("#/$defs/"):
            return _resolve_local_refs(root["$defs"][value["$ref"].rsplit("/", 1)[-1]], root)
        return {key: _resolve_local_refs(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_local_refs(item, root) for item in value]
    return value


def test_operator_catalog_schema_is_valid_and_catalog_conforms():
    schema = _load(CATALOG_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(operator_catalog())


def test_operator_catalog_is_stable_and_defensive():
    first = operator_catalog()
    assert first["schema_version"] == 1
    assert first["workflow_version"] == 1
    assert [item["name"] for item in first["operators"]] == [
        "buffer",
        "dissolve",
        "geometry_metrics",
        "summarize_points_within",
        "join_points_to_polygons",
        "nearest",
        "reproject",
        "clip",
    ]

    assert all(
        "sensitive" in parameter
        for operator in first["operators"]
        for parameter in operator["parameters"]
    )

    first["operators"][0]["parameters"][0]["schema"]["exclusiveMinimum"] = -1
    assert operator_catalog()["operators"][0]["parameters"][0]["schema"] == {
        "type": "number",
        "exclusiveMinimum": 0,
    }


def test_runtime_registry_and_workflow_schema_describe_the_same_contracts():
    workflow_schema, contracts = _workflow_contracts()
    assert set(contracts) == set(OPERATOR_REGISTRY)

    for name, spec in OPERATOR_REGISTRY.items():
        definition = contracts[name]
        input_schema = definition["properties"]["inputs"]
        parameter_schema = definition["properties"].get(
            "parameters",
            {"properties": {}, "required": []},
        )
        required_parameters = set(parameter_schema.get("required", []))

        assert set(input_schema["required"]) == set(spec.input_names)
        assert set(parameter_schema.get("properties", {})) == {
            parameter.name for parameter in spec.parameters
        }
        for parameter in spec.parameters:
            assert parameter.schema == _resolve_local_refs(
                parameter_schema["properties"][parameter.name],
                workflow_schema,
            )
            assert parameter.required is (parameter.name in required_parameters)


def test_compatibility_maps_are_derived_from_registry():
    assert set(OPERATORS) == set(OPERATOR_REGISTRY)
    assert OPERATOR_INPUTS == {
        name: spec.input_names for name, spec in OPERATOR_REGISTRY.items()
    }
    assert OPERATOR_PARAMETER_SPECS == {
        name: {
            "required": spec.required_parameters,
            "optional": spec.optional_parameters,
        }
        for name, spec in OPERATOR_REGISTRY.items()
    }


def test_operators_command_prints_catalog_as_json(capsys):
    result = main(["operators"])
    captured = capsys.readouterr()

    assert result == 0
    assert json.loads(captured.out) == operator_catalog()
    assert captured.err == ""


def test_operators_command_writes_catalog_to_file(tmp_path, capsys):
    destination = tmp_path / "operators.json"
    result = main(["operators", "--output", str(destination)])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out.strip() == str(destination)
    assert captured.err == ""
    assert _load(destination) == operator_catalog()
