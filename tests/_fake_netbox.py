"""An in-memory stand-in for the parts of a ``pynetbox.api`` the NetBox client uses.

Records are snapshots, like pynetbox's: a record read before a change does not
see it. Cables keep both ends' ``cable`` and ``link_peers`` up to date, the way
NetBox does.
"""

from __future__ import annotations

import copy
import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


class Record(SimpleNamespace):
    def __init__(self, endpoint, data):
        super().__init__(**copy.deepcopy(data))
        self._endpoint = endpoint

    def __deepcopy__(self, memo):
        return self  # already a snapshot

    # Fields a save writes back; the others are read-only views of related objects.
    _SAVED = ("name", "custom_fields")

    def save(self):
        row = self._endpoint.rows[self.id]
        row.update({k: copy.deepcopy(getattr(self, k)) for k in self._SAVED if k in row})
        return True

    def delete(self):
        self._endpoint.delete(self.id)
        return True

    def __str__(self):
        return getattr(self, "name", None) or str(self.id)


class Endpoint:
    def __init__(self, nb, name):
        self.nb = nb
        self.name = name
        self.rows: dict[int, dict] = {}

    def _record(self, row):
        return Record(self, self.nb.expand(self.name, row))

    def _matches(self, row, filters):
        full = self.nb.expand(self.name, row)
        for key, want in filters.items():
            if key == "site":
                have = (full.get("site") or full["device"].site).slug
            elif key == "site_id":
                have = (full.get("site") or full["device"].site).id
            elif key.endswith("_id") and key[:-3] in row:
                have = row[key[:-3]]
            else:
                have = row.get(key)
            if have not in (want if isinstance(want, list) else [want]):
                return False
        return True

    # Iterators, like pynetbox's RecordSet: no indexing, one pass.
    def all(self):
        return iter([self._record(r) for r in self.rows.values()])

    def filter(self, **filters):
        return iter([self._record(r) for r in self.rows.values() if self._matches(r, filters)])

    def get(self, **filters):
        found = list(self.filter(**filters))
        if len(found) > 1:
            raise ValueError("get() returned more than one result")
        return found[0] if found else None

    def create(self, **data):
        if self.name == "devices" and list(self.filter(name=data["name"], site_id=data["site"])):
            raise RuntimeError("Device name must be unique per site and tenant.")
        if self.name in ("manufacturers", "device_roles") and list(self.filter(name=data["name"])):
            raise RuntimeError(f"{self.name} with this name already exists.")
        row = {"id": next(_ids), **copy.deepcopy(data)}
        if self.name == "cables":
            self.nb.connect(row)
        else:
            row.setdefault("cable", None)
            if self.name in ("devices", *FakeNetBox._TERMINATION.values()):
                row.setdefault("custom_fields", {})
            if self.name == "devices":
                row.setdefault("primary_ip", None)
            if self.name == "console_ports" and "speed" in row:
                # NetBox returns a choice field as a value/label pair.
                row["speed"] = SimpleNamespace(value=row["speed"], label=f"{row['speed']} bps")
        self.rows[row["id"]] = row
        return self._record(row)

    def delete(self, id_):
        row = self.rows.pop(id_)
        if self.name == "cables":
            self.nb.disconnect(row)


class FakeNetBox:
    def __init__(self):
        endpoints = (
            "sites",
            "devices",
            "device_roles",
            "manufacturers",
            "device_types",
            "power_outlets",
            "power_ports",
            "console_ports",
            "console_server_ports",
            "cables",
        )
        self.dcim = SimpleNamespace(**{n: Endpoint(self, n) for n in endpoints})
        self.extras = SimpleNamespace(custom_fields=Endpoint(self, "custom_fields"))

    _TERMINATION = {
        "dcim.powerport": "power_ports",
        "dcim.poweroutlet": "power_outlets",
        "dcim.consoleport": "console_ports",
        "dcim.consoleserverport": "console_server_ports",
    }

    def _end(self, termination):
        return getattr(self.dcim, self._TERMINATION[termination["object_type"]]).rows[
            termination["object_id"]
        ]

    def connect(self, cable):
        (a,), (b,) = cable["a_terminations"], cable["b_terminations"]
        for end, peer in ((a, b), (b, a)):
            row = self._end(end)
            if row["cable"] is not None:
                raise RuntimeError("NetBox rejected the request: termination already cabled")
            row["cable"] = cable["id"]
            row["_peer"] = peer

    def disconnect(self, cable):
        for end in (*cable["a_terminations"], *cable["b_terminations"]):
            row = self._end(end)
            row["cable"] = None
            row.pop("_peer", None)

    def expand(self, endpoint, row):
        """The row as the API returns it: related objects nested, cable peers listed."""
        out = {k: v for k, v in row.items() if not k.startswith("_")}
        if endpoint in self._TERMINATION.values():
            out["device"] = self.dcim.devices._record(self.dcim.devices.rows[row["device"]])
            out["cable"] = SimpleNamespace(id=row["cable"]) if row["cable"] else None
            peer = row.get("_peer")
            out["link_peers"] = [self._peer_view(peer)] if peer else []
        if endpoint == "devices":
            out["site"] = self.dcim.sites._record(self.dcim.sites.rows[row["site"]])
            for key, related in (("role", "device_roles"), ("device_type", "device_types")):
                rows = getattr(self.dcim, related).rows
                out[key] = (
                    getattr(self.dcim, related)._record(rows[row[key]]) if row.get(key) else None
                )
        return out

    def _peer_view(self, termination):
        row = self._end(termination)
        device = self.dcim.devices.rows[row["device"]]
        return SimpleNamespace(
            id=row["id"],
            name=row["name"],
            device=SimpleNamespace(id=device["id"], name=device["name"]),
        )

    # Helpers for test setup.

    def add_site(self, slug):
        return self.dcim.sites.create(slug=slug, name=slug.upper())

    def add_device(self, name, site, *, custom_fields=None, primary_ip=None):
        d = self.dcim.devices.create(name=name, site=site.id, custom_fields=custom_fields or {})
        if primary_ip:
            self.dcim.devices.rows[d.id]["primary_ip"] = SimpleNamespace(address=primary_ip)
        return self.dcim.devices._record(self.dcim.devices.rows[d.id])
