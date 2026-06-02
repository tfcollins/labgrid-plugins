"""Labgrid plugin package for Analog Devices, Inc. (ADI) specific plugins.

Importing this package registers all ADI drivers, resources, and
strategies with labgrid's ``target_factory`` (via the subpackage imports
below). Upstream labgrid has no entry-point plugin discovery, so this
self-registration — together with a labgrid ``imports: [adi_lg_plugins]``
config key — is how these plugins become resolvable by name.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Import the subpackages for their registration side effects. Order is not
# significant; each guards its own optional-dependency failures.
from . import drivers, resources, strategies  # noqa: E402,F401
