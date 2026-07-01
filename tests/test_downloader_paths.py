from pathlib import Path

from conciliacion_memo_panoptic.panoptic.filenames import (
    build_target_path,
    sanitize_filename,
)


def test_sanitize_filename_replaces_invalid_chars():
    assert sanitize_filename('Soriana:Retail/2026?.xlsx') == "Soriana_Retail_2026_.xlsx"


def test_build_target_path_includes_memo_and_vendor(tmp_path: Path):
    path = build_target_path(
        tmp_path,
        "Soriana_Retail.xlsx",
        memo="030",
        vendor="303452",
    )

    assert path.parent == tmp_path
    assert "MEMO-030" in path.name
    assert "VENDOR-303452" in path.name
    assert path.name.endswith("Soriana_Retail.xlsx")
