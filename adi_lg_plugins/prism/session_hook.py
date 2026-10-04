"""pytest-prism session hook for labgrid hardware runs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from adi_lg_plugins.hw_ci.coordinator import fetch_raw_places

from .capture import CaptureResult, capture_dmesg_ssh, copy_console_logs, dmesg_delta, safe_iio_uri

_SAFE_TAGS = {
    "board-location",
    "boot-strategy",
    "carrier",
    "daughter-board",
    "disabled",
    "hdl-config",
    "runner",
}


def _place(config: Any) -> str | None:
    # Explicit selection is mandatory: silently falling back to LG_PLACE can
    # report a different reservation than the one pytest-prism was asked to use.
    return getattr(config, "labgrid_place", None)


def _coordinator() -> str | None:
    return os.environ.get("LG_COORDINATOR") or os.environ.get("ADI_LG_COORDINATOR")


def _safe_place_metadata(place: str, coordinator: str | None) -> dict[str, Any]:
    if not coordinator:
        return {}
    try:
        places = fetch_raw_places(coordinator, timeout=5.0)
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        return {"metadata_status": "unavailable"}
    raw = next((item for item in places if item.get("name") == place), None)
    if raw is None:
        return {}
    raw_tags_obj = raw.get("tags")
    raw_tags: dict[Any, Any] = raw_tags_obj if isinstance(raw_tags_obj, dict) else {}
    tags = {str(key): str(value) for key, value in raw_tags.items() if key in _SAFE_TAGS}
    matches_obj = raw.get("matches")
    matches: list[Any] = matches_obj if isinstance(matches_obj, list) else []
    exporters = sorted(
        {
            str(match["exporter"])
            for match in matches
            if isinstance(match, dict) and match.get("exporter")
        }
    )
    metadata: dict[str, Any] = {
        "tags": tags,
        "acquired": bool(raw.get("acquired")),
        "exporters": exporters,
    }
    return metadata


class LabgridSessionHook:
    """Add allowlisted allocation context and DUT logs to a Prism run."""

    name = "labgrid"

    def __init__(self) -> None:
        self._before = CaptureResult(False, b"", "none", "not attempted")

    def _dmesg(self, ctx: Any) -> CaptureResult:
        return capture_dmesg_ssh(
            os.environ.get("IIO_URI"),
            user=getattr(ctx.config, "dmesg_ssh_user", "root"),
            key=getattr(ctx.config, "dmesg_ssh_key", None),
        )

    def session_pre(self, ctx: Any) -> dict[str, Any]:
        if getattr(ctx.config, "no_labgrid", False):
            return {"enabled": False, "reason": "disabled"}

        place = _place(ctx.config)
        if not place:
            return {"enabled": False, "reason": "no explicit place selected"}

        coordinator = _coordinator()
        mode = getattr(ctx.config, "dmesg_via", "auto")
        result: dict[str, Any] = {
            "enabled": True,
            "place": place,
            "coordinator_configured": coordinator is not None,
            "environment": Path(os.environ["LG_ENV"]).name if os.environ.get("LG_ENV") else None,
            "iio_uri": safe_iio_uri(os.environ.get("IIO_URI")),
            "dmesg_via": mode,
            **_safe_place_metadata(place, coordinator),
        }
        result = {key: value for key, value in result.items() if value is not None}
        ctx.hook_dir.mkdir(parents=True, exist_ok=True)

        if mode in {"auto", "ssh"}:
            self._before = self._dmesg(ctx)
            if self._before.ok:
                (ctx.hook_dir / "dmesg_pre.log").write_bytes(self._before.output)
                result["dmesg_pre_via"] = self._before.method
            else:
                result["dmesg_pre_error"] = self._before.error

        (ctx.hook_dir / "metadata.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    def session_post(self, ctx: Any) -> dict[str, Any]:
        if getattr(ctx.config, "no_labgrid", False):
            return {"enabled": False, "reason": "disabled"}
        place = _place(ctx.config)
        if not place:
            return {"enabled": False, "reason": "no explicit place selected"}

        mode = getattr(ctx.config, "dmesg_via", "auto")
        result: dict[str, Any] = {"enabled": True, "place": place, "dmesg_via": mode}
        if mode not in {"auto", "ssh", "console", "none"}:
            result["error"] = "unsupported capture mode"
            return result

        console_dir = os.environ.get("PRISM_LABGRID_LOG_DIR")
        console_logs = copy_console_logs(
            Path(console_dir) if console_dir else None,
            ctx.hook_dir,
        )
        result["console_logs"] = console_logs

        if mode in {"auto", "ssh"}:
            after = self._dmesg(ctx)
            if after.ok:
                (ctx.hook_dir / "dmesg_post.log").write_bytes(after.output)
                result["dmesg_post_via"] = after.method
                if self._before.ok:
                    delta = dmesg_delta(self._before.output, after.output)
                    (ctx.hook_dir / "dmesg_diff.log").write_bytes(delta)
                    result["dmesg_diff_bytes"] = len(delta)
            else:
                result["dmesg_post_error"] = after.error
                if mode == "auto" and console_logs:
                    result["fallback"] = "console_logs"
        elif mode == "console" and not console_logs:
            result["error"] = "no console logs; set PRISM_LABGRID_LOG_DIR and pytest --lg-log"

        return result
