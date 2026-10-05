from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import venv
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_NAME = "bundle-manifest.json"
_BUNDLE_SCRIPT_PATHS = (
    Path("scripts/independent_reproduction.py"),
    Path("scripts/reproduce_installed_core.py"),
    Path("scripts/check_reproduction_report.py"),
    Path("schemas/reproduction-report-v1.schema.json"),
)
_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise RuntimeError("wheel must contain exactly one .dist-info/METADATA file")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
    match = re.search(r"^Version:\s*(\S+)\s*$", metadata, re.MULTILINE)
    if match is None:
        raise RuntimeError("wheel metadata is missing Version")
    return match.group(1)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    return info


def _instructions(
    *,
    revision: str,
    wheel_name: str,
    dependency_mode: str,
) -> str:
    dependency_requirement = (
        "- no network access is required; dependency wheels are bundled and hash-verified"
        if dependency_mode == "offline-wheelhouse"
        else "- network access is required for Starshine runtime dependencies and jsonschema"
    )
    return f"""# Starshine independent reproduction bundle

Source revision: {revision}
Wheel: {wheel_name}
Dependency install mode: {dependency_mode}

This bundle is designed to be copied to a machine or CI project outside the Starshine repository.

Requirements:
- Python 3.10 or newer
{dependency_requirement}
- no Starshine source checkout on PYTHONPATH

Run:

    python scripts/independent_reproduction.py run --output-dir evidence

The runner verifies every bundled file against bundle-manifest.json, creates a fresh virtual
environment, installs the bundled wheel non-editably, confirms that starshine_geo imports from that
virtual environment, runs Doctor and the installed-core reproduction harness, validates the
reproduction report, and writes evidence/independent-reproduction-evidence.json.

The evidence JSON intentionally records only relative artifact names, hashes, version/platform
metadata, and pass/fail fields. It does not record the local home-directory or virtual-environment
path.
"""


def build_bundle(
    *,
    wheel: Path,
    revision: str,
    output: Path,
    root: Path = ROOT,
    wheelhouse: Path | None = None,
) -> dict[str, Any]:
    wheel = wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise RuntimeError(f"wheel does not exist: {wheel}")
    if _REVISION_PATTERN.fullmatch(revision) is None:
        raise RuntimeError("revision must be an exact 40-character lowercase Git commit SHA")

    wheel_version = _wheel_version(wheel)
    members: dict[str, bytes] = {}
    for relative in _BUNDLE_SCRIPT_PATHS:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"missing bundle source file: {relative.as_posix()}")
        members[relative.as_posix()] = path.read_bytes()

    wheel_member = f"artifacts/{wheel.name}"
    members[wheel_member] = wheel.read_bytes()

    wheelhouse_members: list[str] = []
    if wheelhouse is not None:
        wheelhouse = wheelhouse.resolve()
        if not wheelhouse.is_dir():
            raise RuntimeError(f"wheelhouse does not exist: {wheelhouse}")
        dependency_wheels = sorted(
            path for path in wheelhouse.iterdir() if path.is_file() and path.suffix == ".whl"
        )
        if not dependency_wheels:
            raise RuntimeError("wheelhouse must contain at least one dependency wheel")
        for dependency_wheel in dependency_wheels:
            if dependency_wheel.name == wheel.name:
                raise RuntimeError("wheelhouse must not duplicate the Starshine wheel")
            member = f"wheelhouse/{dependency_wheel.name}"
            members[member] = dependency_wheel.read_bytes()
            wheelhouse_members.append(member)

    dependency_mode = "offline-wheelhouse" if wheelhouse_members else "network"
    members["INSTRUCTIONS.md"] = _instructions(
        revision=revision,
        wheel_name=wheel.name,
        dependency_mode=dependency_mode,
    ).encode("utf-8")

    file_hashes = {name: _sha256_bytes(data) for name, data in sorted(members.items())}
    manifest = {
        "schema_version": 1,
        "source_revision": revision,
        "starshine_version": wheel_version,
        "wheel": {
            "filename": wheel.name,
            "path": wheel_member,
            "sha256": file_hashes[wheel_member],
        },
        "dependency_install": {
            "mode": dependency_mode,
        },
        "files": file_hashes,
    }
    if wheelhouse_members:
        manifest["wheelhouse"] = {
            "files": wheelhouse_members,
        }
    members[_MANIFEST_NAME] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, mode="w") as archive:
        for name in sorted(members):
            archive.writestr(_zip_info(name), members[name])

    return manifest


def _bundle_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not (root / _MANIFEST_NAME).is_file():
        raise RuntimeError(
            "run mode must be executed from an extracted independent reproduction bundle"
        )
    return root


def verify_bundle(root: Path) -> dict[str, Any]:
    manifest_path = root / _MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported independent reproduction bundle schema")
    revision = manifest.get("source_revision")
    if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
        raise RuntimeError("bundle manifest contains an invalid source revision")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("bundle manifest does not declare file hashes")

    for relative, expected in sorted(files.items()):
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise TypeError("bundle manifest file hashes must be string pairs")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise RuntimeError(f"bundle member escapes root: {relative}")
        if not path.is_file():
            raise RuntimeError(f"bundle member is missing: {relative}")
        actual = _sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"bundle member digest mismatch: {relative}")

    wheel = manifest.get("wheel")
    if not isinstance(wheel, dict):
        raise TypeError("bundle manifest is missing wheel metadata")
    wheel_path = (root / str(wheel.get("path", ""))).resolve()
    if not wheel_path.is_relative_to(root.resolve()):
        raise RuntimeError("bundle wheel path escapes root")
    if not wheel_path.is_file():
        raise RuntimeError("bundle wheel is missing")
    if wheel.get("sha256") != _sha256_file(wheel_path):
        raise RuntimeError("bundle wheel digest does not match manifest")
    if wheel.get("filename") != wheel_path.name:
        raise RuntimeError("bundle wheel filename does not match manifest")
    if manifest.get("starshine_version") != _wheel_version(wheel_path):
        raise RuntimeError("bundle Starshine version does not match wheel metadata")

    dependency_install = manifest.get("dependency_install", {"mode": "network"})
    if not isinstance(dependency_install, dict):
        raise TypeError("bundle dependency-install metadata must be an object")
    dependency_mode = dependency_install.get("mode", "network")
    if dependency_mode not in {"network", "offline-wheelhouse"}:
        raise RuntimeError("bundle dependency-install mode is not supported")

    wheelhouse = manifest.get("wheelhouse")
    if dependency_mode == "offline-wheelhouse":
        if not isinstance(wheelhouse, dict):
            raise TypeError("offline bundle is missing wheelhouse metadata")
        declared = wheelhouse.get("files")
        if not isinstance(declared, list) or not declared:
            raise RuntimeError("offline bundle wheelhouse must declare dependency wheels")
        declared_members: set[str] = set()
        for relative in declared:
            if not isinstance(relative, str) or not relative.startswith("wheelhouse/"):
                raise RuntimeError("offline wheelhouse member path is invalid")
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()):
                raise RuntimeError("offline wheelhouse member escapes bundle root")
            if path.suffix != ".whl" or not path.is_file():
                raise RuntimeError(f"offline wheelhouse member is invalid: {relative}")
            if relative not in files:
                raise RuntimeError(f"offline wheelhouse member is not hash-declared: {relative}")
            declared_members.add(relative)
        actual_members = {
            f"wheelhouse/{path.name}"
            for path in (root / "wheelhouse").glob("*.whl")
            if path.is_file()
        }
        if actual_members != declared_members:
            raise RuntimeError("offline wheelhouse contents do not match the manifest")
    elif wheelhouse is not None:
        raise RuntimeError("network bundle must not declare a wheelhouse")

    return manifest


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _venv_starshine(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "starshine.exe"
    return root / "bin" / "starshine"


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stdout = result.stdout.strip() or "<empty>"
        stderr = result.stderr.strip() or "<empty>"
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {command[0]}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return result


def run_bundle(*, output_dir: Path) -> dict[str, Any]:
    root = _bundle_root()
    manifest = verify_bundle(root)
    wheel_path = root / manifest["wheel"]["path"]

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    doctor_path = output_dir / "doctor-report.json"
    report_path = output_dir / "reproduction-report.json"
    evidence_path = output_dir / "independent-reproduction-evidence.json"

    with tempfile.TemporaryDirectory(prefix="starshine-independent-") as directory:
        environment = Path(directory) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _venv_python(environment)
        starshine = _venv_starshine(environment)

        dependency_install = manifest.get("dependency_install", {"mode": "network"})
        dependency_mode = dependency_install.get("mode", "network")
        if dependency_mode == "offline-wheelhouse":
            install_env = os.environ.copy()
            install_env["PIP_NO_INDEX"] = "1"
            install_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
            _run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    str(root / "wheelhouse"),
                    str(wheel_path),
                    "jsonschema>=4.23,<5",
                ],
                env=install_env,
            )
        else:
            _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
            _run([str(python), "-m", "pip", "install", str(wheel_path), "jsonschema>=4.23,<5"])

        package_location = _run(
            [
                str(python),
                "-c",
                (
                    "import pathlib,starshine_geo;"
                    "print(pathlib.Path(starshine_geo.__file__).resolve())"
                ),
            ]
        ).stdout.strip()
        package_path = Path(package_location).resolve()
        if not package_path.is_relative_to(environment.resolve()):
            raise RuntimeError(
                "installed starshine_geo is not imported from the clean virtual environment"
            )

        version_result = _run([str(starshine), "--version"]).stdout.strip()
        doctor = _run([str(starshine), "doctor", "--format", "json"])
        doctor_report = json.loads(doctor.stdout)
        if not doctor_report.get("valid"):
            raise RuntimeError("installed Starshine doctor did not pass")
        doctor_path.write_text(
            json.dumps(doctor_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        reproduce_script = root / "scripts" / "reproduce_installed_core.py"
        installed_env = os.environ.copy()
        installed_env["PATH"] = (
            str(starshine.parent)
            + os.pathsep
            + installed_env.get("PATH", "")
        )
        _run(
            [str(python), str(reproduce_script), "--output", str(report_path)],
            cwd=output_dir,
            env=installed_env,
        )
        checker = root / "scripts" / "check_reproduction_report.py"
        _run([str(python), str(checker), str(report_path)], cwd=output_dir)
        reproduction_report = json.loads(report_path.read_text(encoding="utf-8"))

        evidence = {
            "schema_version": 1,
            "status": "ok",
            "source_revision": manifest["source_revision"],
            "starshine_version": manifest["starshine_version"],
            "starshine_version_output": version_result,
            "wheel_filename": manifest["wheel"]["filename"],
            "wheel_sha256": manifest["wheel"]["sha256"],
            "dependency_install_mode": dependency_mode,
            "python": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
            },
            "platform": {
                "system": platform.system() or "unknown",
                "machine": platform.machine() or "unknown",
            },
            "installed_from_clean_venv": True,
            "doctor_valid": True,
            "doctor_report_sha256": _sha256_file(doctor_path),
            "reproduction_report_sha256": _sha256_file(report_path),
            "reproduction_output_digest": reproduction_report["output_digest"],
            "reproduced_steps": reproduction_report["reproduced_steps"],
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(evidence_path)
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare or run a portable Starshine independent-reproduction bundle"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bundle = subparsers.add_parser("bundle", help="build a deterministic handoff ZIP")
    bundle.add_argument("--wheel", type=Path, required=True)
    bundle.add_argument("--revision", required=True)
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument(
        "--wheelhouse",
        type=Path,
        default=None,
        help="optional directory of dependency wheels for a hash-verified offline bundle",
    )

    run = subparsers.add_parser("run", help="execute an extracted bundle in a clean virtualenv")
    run.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evidence"),
        help="directory for doctor, reproduction, and evidence JSON reports",
    )

    args = parser.parse_args(argv)
    if args.command == "bundle":
        manifest = build_bundle(
            wheel=args.wheel,
            revision=args.revision,
            output=args.output,
            wheelhouse=args.wheelhouse,
        )
        print(
            f"{args.output} ({manifest['starshine_version']} @ "
            f"{manifest['source_revision']})"
        )
        return 0
    run_bundle(output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
