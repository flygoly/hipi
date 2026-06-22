"""Tests for application icon path resolution."""

from hipi.icon_paths import find_icon_path, icon_paths


def test_icon_paths_include_packaging_svg():
    paths = icon_paths()
    assert any("packaging" in str(p) and p.name == "hipi.svg" for p in paths)


def test_find_icon_path_in_dev_tree():
    path = find_icon_path()
    assert path is not None
    assert path.name == "hipi.svg"
    assert path.is_file()
