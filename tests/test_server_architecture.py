from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "src" / "starshine_geo"
SERVER_ROOT = ROOT / "src" / "starshine_server"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_core_never_depends_on_the_server_adapter() -> None:
    violations = []
    for path in CORE_ROOT.rglob("*.py"):
        if any(name.startswith("starshine_server") for name in _imports(path)):
            violations.append(path.relative_to(ROOT).as_posix())

    assert violations == []


def test_server_uses_the_public_core_boundary_only() -> None:
    violations = []
    for path in SERVER_ROOT.rglob("*.py"):
        for name in _imports(path):
            if name.startswith("starshine_geo."):
                violations.append((path.relative_to(ROOT).as_posix(), name))

    assert violations == []


def test_server_does_not_import_spatial_backends_directly() -> None:
    forbidden = {"shapely", "pyproj", "geopandas", "pyogrio"}
    violations = []
    for path in SERVER_ROOT.rglob("*.py"):
        imported = {name.split(".", 1)[0] for name in _imports(path)}
        if imported & forbidden:
            violations.append(path.relative_to(ROOT).as_posix())

    assert violations == []


def test_execution_worker_has_no_shell_or_network_dependencies() -> None:
    worker = SERVER_ROOT / "worker.py"
    imported = {name.split(".", 1)[0] for name in _imports(worker)}

    assert imported.isdisjoint(
        {"subprocess", "socket", "urllib", "requests", "httpx", "fastapi"}
    )


def test_execution_supervisor_uses_one_fixed_non_shell_worker_entrypoint() -> None:
    execution_path = SERVER_ROOT / "execution.py"
    source = execution_path.read_text(encoding="utf-8")

    assert source.count("subprocess.Popen(") == 1
    assert '"-m",\n            "starshine_server.worker"' in source
    assert "shell=False" in source
    assert "shell=True" not in source
    assert "eval(" not in source
    assert "exec(" not in source
