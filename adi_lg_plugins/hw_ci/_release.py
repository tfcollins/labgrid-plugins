"""Single source for the consumer-facing release pin.

``RECOMMENDED_PIN`` is the latest STABLE release tag consumers should pin the
reusable workflows to (``uses: …@<pin>``). Bump it as the final step of a
release (see RELEASING.md). The docs ``|hw_ci_pin|`` substitution and the
pin-consistency lint both read this value, so a release bump touches one line.
"""

from __future__ import annotations

RECOMMENDED_PIN = "v3.5"
