import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "workflow-v1.schema.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "workflows"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_workflow_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(_load(SCHEMA_PATH))


def test_valid_workflow_fixtures_pass_external_schema_validation():
    validator = Draft202012Validator(_load(SCHEMA_PATH))
    fixtures = sorted(FIXTURE_DIR.glob("valid-*.json"))

    assert fixtures
    for fixture in fixtures:
        errors = sorted(validator.iter_errors(_load(fixture)), key=lambda error: list(error.path))
        assert errors == [], f"{fixture.name}: {[error.message for error in errors]}"


def test_invalid_workflow_fixtures_fail_external_schema_validation():
    validator = Draft202012Validator(_load(SCHEMA_PATH))
    fixtures = sorted(FIXTURE_DIR.glob("invalid-*.json"))

    assert fixtures
    for fixture in fixtures:
        assert list(validator.iter_errors(_load(fixture))), fixture.name
