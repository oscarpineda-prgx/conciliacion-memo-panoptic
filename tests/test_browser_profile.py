from pathlib import Path

from conciliacion_memo_panoptic.panoptic.browser import make_unique_profile_dir


def test_make_unique_profile_dir_uses_unique_subfolder(tmp_path: Path):
    base_dir = tmp_path / "panoptic-profile-edge"

    first = make_unique_profile_dir(base_dir)
    second = make_unique_profile_dir(base_dir)

    assert first.parent == base_dir.parent
    assert first.name.startswith("panoptic-profile-edge-")
    assert first != second
