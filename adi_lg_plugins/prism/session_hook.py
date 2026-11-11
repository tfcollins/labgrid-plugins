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


def _iio_uri() -> str:
    uri = os.environ.get("IIO_URI_OVERRIDE") or os.environ.get("IIO_URI")
    if uri:
        return uri
    config = os.environ.get("LG_ENV")
    if not config:
        raise RuntimeError("no IIO URI or labgrid environment is configured")

    from labgrid import Environment

    from adi_lg_plugins.request.uri import resolve_uri

    env = Environment(config)
    try:
        return resolve_uri(env.get_target(), wait=0, allow_static=False)
    finally:
        env.cleanup()


def _safe_place_metadata(place: str, coordinator: str | None) -> dict[str, Any]:
    if not coordinator:
        return {"metadata_status": "unavailable", "metadata_error": "coordinator is not configured"}
    try:
        places = fetch_raw_places(coordinator, timeout=5.0)
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        return {
            "metadata_status": "unavailable",
            "metadata_error": f"coordinator lookup failed ({type(exc).__name__})",
        }
    raw = next((item for item in places if item.get("name") == place), None)
    if raw is None:
        return {"metadata_status": "unavailable", "metadata_error": "selected place was not found"}
    raw_tags_obj = raw.get("tags")
    raw_tags: dict[Any, Any] = raw_tags_obj if isinstance(raw_tags_obj, dict) else {}
    tags = {str(key): str(value) for key, value in raw_tags.items() if key in _SAFE_TAGS}
    matches_obj = raw.get("matches")
    matches: list[Any] = matches_obj if isinstance(matches_obj, list) else []
    resources = raw.get("acquired_resources") or []
    acquired_exporters = {
        str(resource[0])
        for resource in resources
        if isinstance(resource, (list, tuple)) and resource and resource[0]
    }
    exporters = sorted(
        acquired_exporters
        or {
            str(match["exporter"])
            for match in matches
            if isinstance(match, dict)
            and match.get("exporter")
            and not any(char in str(match["exporter"]) for char in "*?[")
        }
    )
    metadata: dict[str, Any] = {
        "metadata_status": "ok",
        "tags": tags,
        "board": tags.get("daughter-board"),
        "carrier": tags.get("carrier"),
        "acquired": bool(raw.get("acquired")),
        "exporters": exporters,
    }
    if len(exporters) == 1:
        metadata["exporter"] = exporters[0]
    if not exporters:
        metadata["exporter_error"] = "coordinator did not return a concrete exporter"
    return {key: value for key, value in metadata.items() if value is not None}


class LabgridSessionHook:
    """Add allowlisted allocation context and DUT logs to a Prism run."""

    name = "labgrid"

    def __init__(self) -> None:
        self._before = CaptureResult(False, b"", "none", "not attempted")
        self._metadata: dict[str, Any] = {}

    def _record(self, ctx: Any, result: dict[str, Any]) -> dict[str, Any]:
        self._metadata.update(result)
        self._metadata["collection_errors"] = [
            f"{key}: {value}"
            for key, value in self._metadata.items()
            if (key.endswith("_error") or key == "error") and value
        ]
        ctx.hook_dir.mkdir(parents=True, exist_ok=True)
        (ctx.hook_dir / "metadata.json").write_text(
            json.dumps(self._metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return dict(self._metadata)

    def _dmesg(self, ctx: Any) -> CaptureResult:
        try:
            uri = _iio_uri()
        except Exception as exc:
            return CaptureResult(False, b"", "ssh", f"DUT URI lookup failed ({type(exc).__name__})")
        self._metadata["iio_uri"] = safe_iio_uri(uri)
        return capture_dmesg_ssh(
            uri,
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
            "iio_uri": safe_iio_uri(
                os.environ.get("IIO_URI_OVERRIDE") or os.environ.get("IIO_URI")
            ),
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

        return self._record(ctx, result)

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
            return self._record(ctx, result)

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

        return self._record(ctx, result)
