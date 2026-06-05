from dataclasses import dataclass

import pytest

from adi_lg_plugins.hw_ci.noos_manifest import (
    NoOSLeg,
    NoOSProject,
    build_noos_matrix,
    load_noos_manifest,
)


@dataclass
class _Match:
    satisfiable: bool
    runner: str | None = None
    image: str | None = None
    reservation_filter: dict | None = None


def _write(tmp_path, text):
    p = tmp_path / "projects.yaml"
    p.write_text(text)
    return str(p)


def test_load_defaults_banner_and_build_vars(tmp_path):
    path = _write(
        tmp_path,
        """
projects:
  - noos_project: adrv9009
    part: adrv9009
    carriers: [zc706]
""",
    )
    projects = load_noos_manifest(path)
    assert projects == [
        NoOSProject(
            noos_project="adrv9009",
            part="adrv9009",
            carriers=["zc706"],
            validate_banner="Successfully initialized",
            build_vars={},
        )
    ]


def test_load_explicit_banner_and_build_vars(tmp_path):
    path = _write(
        tmp_path,
        """
projects:
  - noos_project: ad9371
    part: ad9371
    carriers: [zc706]
    validate_banner: "Done"
    build_vars: {EXAMPLE: iio_example}
""",
    )
    proj = load_noos_manifest(path)[0]
    assert proj.validate_banner == "Done"
    assert proj.build_vars == {"EXAMPLE": "iio_example"}


def test_load_rejects_missing_required_key(tmp_path):
    path = _write(tmp_path, "projects:\n  - part: ad9371\n    carriers: [zc706]\n")
    with pytest.raises(ValueError):
        load_noos_manifest(path)


def test_matrix_leg_carries_board_release_banner_build_vars():
    projects = [
        NoOSProject(
            noos_project="ad9371",
            part="ad9371",
            carriers=["zc706"],
            validate_banner="Done",
            build_vars={"EXAMPLE": "iio_example"},
        )
    ]

    def probe(part, carrier):
        return _Match(
            satisfiable=True,
            runner="hw-bq",
            image="2023_R2_P1",
            reservation_filter={"daughter-board": "adrv9371", "carrier": "zc706"},
        )

    legs, missing = build_noos_matrix(projects, probe)
    assert missing == []
    assert legs == [
        NoOSLeg(
            part="ad9371",
            noos_project="ad9371",
            carrier="zc706",
            runner="hw-bq",
            board="adrv9371",
            release="2023_R2_P1",
            validate_banner="Done",
            build_vars={"EXAMPLE": "iio_example"},
        )
    ]
