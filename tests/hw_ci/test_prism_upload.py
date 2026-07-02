"""The vendored Prism uploader is importable and wired as an entry point.

The two vendored modules under ``adi_lg_plugins/hw_ci/prism_upload`` are copied
verbatim from tfcollins/prism and excluded from ruff, so we don't test their
internals here — just that the package imports (the sibling ``_prism_client``
import resolves), the ``main`` entry-point target exists, and the argument parser
accepts the flags the infra-smoke workflow passes.
"""

from __future__ import annotations


def test_vendored_uploader_imports_and_exposes_main():
    from adi_lg_plugins.hw_ci.prism_upload.upload_run import build_parser, main

    assert callable(main)  # entry point: adi_lg_plugins.hw_ci.prism_upload.upload_run:main
    assert build_parser() is not None


def test_parser_accepts_the_flags_infra_smoke_passes():
    from adi_lg_plugins.hw_ci.prism_upload.upload_run import build_parser

    ns = build_parser().parse_args(
        [
            "results-nemo.xml",
            "--url",
            "https://prism.example",
            "--project",
            "lab-infra-daily",
            "--auto-create-project",
            "--run-name",
            "daily-infra-7-nemo",
            "--tag",
            "place=nemo",
            "--tag",
            "board=adrv9009",
        ]
    )
    # parse_args not raising is the point — these flags are the ones the workflow
    # passes. The exact --tag representation is the vendored code's concern.
    assert str(ns.junit) == "results-nemo.xml"
    assert ns.project == "lab-infra-daily"
    assert ns.auto_create_project is True
    assert len(ns.tag) == 2
