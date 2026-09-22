from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.check_reproduction_report import EXPECTED_STEPS, check
from scripts.independent_reproduction import build_bundle, verify_bundle
from scripts.reproduce_installed_core import build_reproduction_report

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "reproduction-report-v1.schema.json"


def test_self_created_installed_core_reproduction_is_schema_checked(tmp_path):
    report = build_reproduction_report()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)

    assert report["status"] == "ok"
    assert report["doctor_valid"] is True
    assert report["output_feature_count"] == 3
    assert report["reproduced_steps"] == EXPECTED_STEPS

    report_path = tmp_path / "reproduction-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    check(report_path)


def _write_fake_wheel(path: Path, *, version: str = "9.8.7.dev0") -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        archive.writestr(
            f"starshine_geo-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: starshine-geo\nVersion: {version}\n",
        )


def _write_bundle_sources(root: Path) -> None:
    for relative in (
        Path("scripts/independent_reproduction.py"),
        Path("scripts/reproduce_installed_core.py"),
        Path("scripts/check_reproduction_report.py"),
        Path("schemas/reproduction-report-v1.schema.json"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture:{relative.as_posix()}\n", encoding="utf-8")


def test_independent_reproduction_bundle_is_deterministic_and_self_verifying(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _write_bundle_sources(root)
    wheel = tmp_path / "starshine_geo-9.8.7.dev0-py3-none-any.whl"
    _write_fake_wheel(wheel)

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    revision = "a" * 40

    manifest = build_bundle(wheel=wheel, revision=revision, output=first, root=root)
    build_bundle(wheel=wheel, revision=revision, output=second, root=root)

    assert first.read_bytes() == second.read_bytes()
    assert manifest["source_revision"] == revision
    assert manifest["starshine_version"] == "9.8.7.dev0"
    assert manifest["wheel"]["filename"] == wheel.name

    extracted = tmp_path / "bundle"
    with zipfile.ZipFile(first) as archive:
        archive.extractall(extracted)
    verified = verify_bundle(extracted)
    assert verified == manifest


def test_independent_reproduction_bundle_rejects_tampered_members(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _write_bundle_sources(root)
    wheel = tmp_path / "starshine_geo-9.8.7.dev0-py3-none-any.whl"
    _write_fake_wheel(wheel)
    bundle = tmp_path / "bundle.zip"
    build_bundle(wheel=wheel, revision="b" * 40, output=bundle, root=root)

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)
    (extracted / "scripts" / "reproduce_installed_core.py").write_text(
        "tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="digest mismatch"):
        verify_bundle(extracted)

def test_independent_reproduction_bundle_rejects_wheel_path_escape(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _write_bundle_sources(root)
    wheel = tmp_path / "starshine_geo-9.8.7.dev0-py3-none-any.whl"
    _write_fake_wheel(wheel)
    bundle = tmp_path / "bundle.zip"
    build_bundle(wheel=wheel, revision="c" * 40, output=bundle, root=root)

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)

    manifest_path = extracted / "bundle-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wheel"]["path"] = "../outside.whl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="wheel path escapes root"):
        verify_bundle(extracted)

