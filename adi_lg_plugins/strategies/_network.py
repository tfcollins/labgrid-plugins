"""Client-local address discovery shared by remote boot strategies."""


def override_networkservice_address(networkservice, ip: str) -> None:
    """Point a (possibly remote) NetworkService at a new IP.

    Setting ``networkservice.address`` alone is not enough when the
    resource came in via a RemotePlace: labgrid's RemotePlaceManager
    polls the coordinator every ``ManagedResource.timeout`` seconds and
    rewrites every attribute from ``resource._remote_entry.args`` back
    onto the live resource (see
    labgrid/resource/remote.py:RemotePlaceManager.poll). Without also
    updating the cached entry, the next poll reverts the address back
    to the exporter's stale record before SSHDriver's on_activate reads
    it — and the control socket ends up wired to the wrong IP.

    Note: ``ResourceEntry.args`` is a *property* that returns a fresh
    copy of ``self.data["params"]`` each call, so mutating
    ``remote_entry.args[...]`` is a no-op. We have to touch the backing
    store at ``remote_entry.data["params"]["address"]`` instead.
    """
    networkservice.address = ip
    remote_entry = getattr(networkservice, "_remote_entry", None)
    if remote_entry is None:
        return
    # ResourceEntry.data["params"] is the dict that ResourceEntry.args
    # (the property) returns a copy of, and that RemotePlaceManager.poll
    # reads via .args on every tick.
    data = getattr(remote_entry, "data", None)
    if isinstance(data, dict):
        params = data.get("params")
        if isinstance(params, dict):
            params["address"] = ip
