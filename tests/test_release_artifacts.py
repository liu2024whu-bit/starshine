"""Synthetic archive probes; no untrusted member is ever extracted."""
from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import check_release_artifacts as inspector

VERSION = "0.8.0.dev0"
ROOT = f"starshine_geo-{VERSION}"


@pytest.mark.parametrize("name", [
    "../escape.txt", "src/../../escape.txt", "/absolute.txt", "C:/escape.txt",
    "C:escape.txt", "src\\escape.txt", "src/./module.py", "src//module.py",
    "", "./", "src/file.py:alternate", "src/trailing. ", "src/new\nline.py",
    "src/.ENV/secret", "src/Archive/data", "src/NUL.txt", "src/com1.py",
])
def test_rejects_unsafe_or_nonportable_member_names(name):
    with pytest.raises(RuntimeError, match="unsafe|forbidden"):
        inspector._validate_member_names([(name, 1)], "probe.zip")


@pytest.mark.parametrize("names", [
    ["src/module.py", "src/module.py"],
    ["src/module.py", "src/MODULE.py"],
    ["src/", "src"],
    ["src/module.py", "SRC/other.py"],
    ["src/file", "src/file/nested.py"],
])
def test_rejects_duplicate_alias_or_file_directory_collisions(names):
    with pytest.raises(RuntimeError, match="duplicate|collision"):
        inspector._validate_member_names([(name, 1) for name in names], "probe.zip")


def test_accepts_regular_canonical_paths_and_explicit_directories():
    inspector._validate_member_names([
        (ROOT + "/", 0), (ROOT + "/src/", 0),
        (ROOT + "/src/package/module.py", 1),
        (ROOT + "/src/package/other.py", 2),
    ], "probe.tar.gz")


@pytest.mark.parametrize("size", [-1, 5 * 1024 * 1024 + 1])
def test_rejects_invalid_member_sizes(size):
    with pytest.raises(RuntimeError, match="size|5 MiB"):
        inspector._validate_member_names([("module.py", size)], "probe.zip")


def _wheel(tmp_path: Path, *, prefix="", mode=None, duplicate=False, omit_asset=None) -> Path:
    path = tmp_path / f"{ROOT}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for name in inspector._package_python_suffixes():
            archive.writestr(prefix + name, "# synthetic module\n")
        for asset in ("index.html", "styles.css", "app.js", "api.js", "render.js"):
            if asset != omit_asset:
                archive.writestr(prefix + f"starshine_server/static/{asset}", "synthetic asset")
        metadata = f"{ROOT}.dist-info/METADATA"
        archive.writestr(metadata, f"Metadata-Version: 2.4\nVersion: {VERSION}\n")
        if duplicate:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(metadata, f"Version: {VERSION}\n")
        if mode is not None:
            item = zipfile.ZipInfo("extra-entry")
            item.create_system = 3
            item.external_attr = (mode | 0o644) << 16
            archive.writestr(item, "target")
    return path


def test_canonical_wheel_still_passes(tmp_path):
    inspector._check_wheel(_wheel(tmp_path), VERSION)


@pytest.mark.parametrize("asset", ["index.html", "styles.css", "app.js", "api.js", "render.js"])
def test_wheel_requires_every_workbench_asset(tmp_path, asset):
    with pytest.raises(RuntimeError, match="missing expected files"):
        inspector._check_wheel(_wheel(tmp_path, omit_asset=asset), VERSION)


def test_prefix_cannot_impersonate_installed_modules(tmp_path):
    with pytest.raises(RuntimeError, match="missing expected files"):
        inspector._check_wheel(_wheel(tmp_path, prefix="not-installed/"), VERSION)


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFSOCK])
def test_zip_rejects_links_and_special_entries(tmp_path, mode):
    with pytest.raises(RuntimeError, match="unsupported archive member type"):
        inspector._check_wheel(_wheel(tmp_path, mode=mode), VERSION)


def test_zip_rejects_duplicate_metadata_before_reading_it(tmp_path):
    with pytest.raises(RuntimeError, match="duplicate"):
        inspector._check_wheel(_wheel(tmp_path, duplicate=True), VERSION)


@pytest.mark.parametrize("member_type", [
    tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE,
])
def test_tar_checks_nonregular_entries_too(tmp_path, member_type):
    path = tmp_path / f"{ROOT}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo(f"{ROOT}/extra-entry")
        item.type = member_type
        item.linkname = "../outside"
        archive.addfile(item)
    with pytest.raises(RuntimeError, match="unsupported archive member type"):
        inspector._check_sdist(path, VERSION, "0.7.0")


def test_tar_rejects_unsafe_directory_without_extracting_it(tmp_path):
    path = tmp_path / f"{ROOT}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo(f"{ROOT}/../../outside/")
        item.type = tarfile.DIRTYPE
        archive.addfile(item)
    with pytest.raises(RuntimeError, match="unsafe"):
        inspector._check_sdist(path, VERSION, "0.7.0")
    assert not (tmp_path / "outside").exists()


def test_sdist_requires_one_expected_root(tmp_path):
    path = tmp_path / f"{ROOT}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        data = b"test"
        item = tarfile.TarInfo("another-project/README.md")
        item.size = len(data)
        archive.addfile(item, io.BytesIO(data))
    with pytest.raises(RuntimeError, match="unexpected sdist root"):
        inspector._check_sdist(path, VERSION, "0.7.0")
