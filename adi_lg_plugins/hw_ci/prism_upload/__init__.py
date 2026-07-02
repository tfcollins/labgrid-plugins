"""Vendored Prism CI uploader (stdlib-only).

``upload_run.py`` and ``_prism_client.py`` are copied **verbatim** from the
``scripts/`` directory of the (private) ``tfcollins/prism`` repository so the
hardware-CI workflows can post JUnit results to a Prism server without cloning
that private repo or pip-installing a package that doesn't exist. They depend
only on the standard library.

Do not hand-edit the two vendored modules — re-sync them from ``tfcollins/prism``
if the upstream uploader changes. They are excluded from ruff (see
``pyproject.toml`` ``[tool.ruff] extend-exclude``) for the same reason.

Invoke via the ``adi-lg-prism-upload`` console script (entry point
``adi_lg_plugins.hw_ci.prism_upload.upload_run:main``).
"""
