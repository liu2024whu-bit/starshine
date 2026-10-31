from pathlib import Path

import pytest

from starshine_geo._path_identity import same_file
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError


def _alias(source, destination, kind):
    if kind == "hardlink":
        destination.hardlink_to(source)
    else:
        destination.symlink_to(source)


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
@pytest.mark.parametrize(
    "command",
    ["inspect", "inventory", "quality", "plan", "graph", "explain", "contract", "preflight"],
)
def test_report_alias_rejected_before_reading(tmp_path, monkeypatch, capsys, kind, command):
    source = tmp_path / "source.json"
    source.write_bytes(b"synthetic unread input")
    output = tmp_path / "output.json"
    _alias(source, output, kind)
    monkeypatch.setattr("starshine_geo.cli.read_json", lambda *a: pytest.fail("input read"))
    monkeypatch.setattr(
        "starshine_geo.cli.inventory_source", lambda *a, **k: pytest.fail("input read")
    )
    assert main([command, str(source), "--output", str(output)]) == 2
    assert "must not overwrite" in capsys.readouterr().err
    assert source.read_bytes() == output.read_bytes() == b"synthetic unread input"


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
@pytest.mark.parametrize("target", ["workflow", "input", "output"])
def test_run_manifest_alias_rejected_before_reading(tmp_path, monkeypatch, capsys, kind, target):
    _run_alias_case(tmp_path, monkeypatch, capsys, kind, target, manifest_alias=True)


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
@pytest.mark.parametrize("target", ["workflow", "input"])
def test_run_output_alias_rejected_before_reading(tmp_path, monkeypatch, capsys, kind, target):
    _run_alias_case(tmp_path, monkeypatch, capsys, kind, target, manifest_alias=False)


def _run_alias_case(tmp_path, monkeypatch, capsys, kind, target, *, manifest_alias):
    paths = {
        name: tmp_path / f"{name}.json" for name in ("workflow", "input", "output", "manifest")
    }
    for name, path in paths.items():
        path.write_text(name, encoding="utf-8")
    alias_name = "manifest" if manifest_alias else "output"
    paths[alias_name].unlink()
    _alias(paths[target], paths[alias_name], kind)
    before = {name: path.read_bytes() for name, path in paths.items()}
    monkeypatch.setattr("starshine_geo.cli.read_json", lambda *a: pytest.fail("input read"))
    assert (
        main(
            [
                "run",
                str(paths["workflow"]),
                "--layer",
                f"source={paths['input']}",
                "--output-layer",
                "result",
                "--output",
                str(paths["output"]),
                "--manifest",
                str(paths["manifest"]),
            ]
        )
        == 2
    )
    assert "must not overwrite" in capsys.readouterr().err
    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_preflight_rejects_input_hardlink(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.json"
    source.write_bytes(b"original")
    output = tmp_path / "report.json"
    output.hardlink_to(source)
    monkeypatch.setattr("starshine_geo.cli.read_json", lambda *a: pytest.fail("input read"))
    assert (
        main(
            [
                "preflight",
                str(tmp_path / "workflow.json"),
                "--layer",
                f"source={source}",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert "must not overwrite an input layer" in capsys.readouterr().err
    assert source.read_bytes() == b"original"


def test_path_identity_distinguishes_new_and_existing_paths(tmp_path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    assert same_file(left, tmp_path / "." / "left.json")
    assert not same_file(left, right)
    left.write_text("same content", encoding="utf-8")
    assert not same_file(left, right)
    right.write_text("same content", encoding="utf-8")
    assert not same_file(left, right)


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("stat failed")])
def test_identity_failure_is_not_silently_treated_as_distinct(tmp_path, monkeypatch, error):
    def fail(*args):
        raise error

    monkeypatch.setattr(Path, "samefile", fail)
    with pytest.raises(ValidationError, match="cannot safely compare"):
        same_file(tmp_path / "left", tmp_path / "right")


def test_new_report_destination_still_works(tmp_path):
    workflow = tmp_path / "workflow.json"
    workflow.write_bytes(
        (Path(__file__).resolve().parents[1] / "examples" / "workflow.json").read_bytes()
    )
    output = tmp_path / "new" / "graph.json"
    assert (
        main(
            [
                "graph",
                str(workflow),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.is_file()


def test_resolution_failure_is_an_expected_validation_error(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("resolution failed")

    monkeypatch.setattr(Path, "resolve", fail)
    with pytest.raises(ValidationError, match="cannot safely compare"):
        same_file(tmp_path / "left", tmp_path / "right")
