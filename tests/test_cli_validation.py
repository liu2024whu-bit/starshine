import json
from pathlib import Path

from starshine_geo.cli import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "workflows"


def test_validate_command_reports_valid_workflow_as_json(capsys):
    result = main(
        [
            "validate",
            str(FIXTURE_DIR / "valid-buffer.json"),
            "--layer-name",
            "source",
            "--diagnostic-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert json.loads(captured.out) == {"valid": True, "workflow_version": 1}
    assert captured.err == ""


def test_validate_command_reports_stable_parameter_diagnostic(capsys):
    result = main(
        [
            "validate",
            str(FIXTURE_DIR / "invalid-buffer-missing-work-crs.json"),
            "--layer-name",
            "source",
            "--diagnostic-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    envelope = json.loads(captured.err)
    assert envelope["error"] == "workflow_validation"
    assert envelope["diagnostic"] == {
        "code": "missing_parameter",
        "message": "missing required parameter for buffer: work_crs",
        "path": "steps[0].parameters.work_crs",
        "step_index": 0,
        "operation": "buffer",
    }
