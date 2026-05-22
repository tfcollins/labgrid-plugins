"""MATLAB hardware-CI launcher for labgrid-managed boards.

A generic, reusable bridge that lets any MATLAB toolbox run its
hardware tests against a board provisioned by labgrid:

* :mod:`~adi_lg_plugins.matlab_ci.board_map` — map a coordinator
  place's tags (carrier / daughter-board / hdl-config) to the toolbox's
  MATLAB board reference name.
* :mod:`~adi_lg_plugins.matlab_ci.discover` — intersect live coordinator
  places with the toolbox's board map and emit a GitHub Actions matrix.
* :mod:`~adi_lg_plugins.matlab_ci.run` — boot a place, resolve the
  booted board's libIIO URI, launch MATLAB with ``IIO_URI`` set, and
  release the place.

It reuses the typed surface in :mod:`adi_lg_plugins.hw_ci`
(``coordinator``, ``schema``, ``render_env``) rather than duplicating it.
"""
