"""Unit tests for adi_lg_plugins.tools.netbox.client.

All exercised against a MagicMock standing in for a pynetbox.api instance -
client.py only imports pynetbox lazily (inside connect()), so these run
without pynetbox installed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from adi_lg_plugins.tools.netbox import client


def test_ensure_schema_creates_missing_objects():
    nb = MagicMock()
    nb.dcim.device_roles.get.return_value = None
    nb.dcim.manufacturers.get.return_value = None
    nb.extras.custom_fields.get.return_value = None

    client.ensure_schema(nb)

    nb.dcim.device_roles.create.assert_called_once()
    assert nb.dcim.device_roles.create.call_args.kwargs["slug"] == client.DEVICE_ROLE_SLUG
    nb.dcim.manufacturers.create.assert_called_once()
    assert nb.extras.custom_fields.create.call_count == len(client.CUSTOM_FIELDS)
    for call in nb.extras.custom_fields.create.call_args_list:
        assert call.kwargs["object_types"] == ["dcim.device"]


def test_ensure_schema_is_idempotent_when_everything_exists():
    nb = MagicMock()
    nb.dcim.device_roles.get.return_value = object()
    nb.dcim.manufacturers.get.return_value = object()
    nb.extras.custom_fields.get.return_value = object()

    client.ensure_schema(nb)

    nb.dcim.device_roles.create.assert_not_called()
    nb.dcim.manufacturers.create.assert_not_called()
    nb.extras.custom_fields.create.assert_not_called()


def test_ensure_device_type_creates_when_missing():
    nb = MagicMock()
    nb.dcim.device_types.get.return_value = None
    nb.dcim.manufacturers.get.return_value = MagicMock(id=7)
    nb.dcim.device_types.create.return_value = MagicMock(id=42)

    result = client.ensure_device_type(nb, "ZCU102")

    assert result == 42
    nb.dcim.device_types.create.assert_called_once_with(
        manufacturer=7, model="ZCU102", slug="zcu102"
    )


def test_ensure_device_type_returns_existing_id_without_creating():
    nb = MagicMock()
    nb.dcim.device_types.get.return_value = MagicMock(id=13)

    result = client.ensure_device_type(nb, "zcu102")

    assert result == 13
    nb.dcim.device_types.create.assert_not_called()


def test_ensure_device_type_requires_manufacturer_first():
    nb = MagicMock()
    nb.dcim.device_types.get.return_value = None
    nb.dcim.manufacturers.get.return_value = None

    with pytest.raises(RuntimeError, match="ensure_schema"):
        client.ensure_device_type(nb, "zcu102")


def test_create_or_update_device_requires_existing_site():
    nb = MagicMock()
    nb.dcim.sites.get.return_value = None

    with pytest.raises(RuntimeError, match="does not exist"):
        client.create_or_update_device(
            nb, "zcu102-lab1", carrier="zcu102", site_slug="lab1", custom_fields={}
        )


def test_create_or_update_device_creates_when_missing():
    nb = MagicMock()
    nb.dcim.sites.get.return_value = MagicMock(id=1)
    nb.dcim.device_types.get.return_value = MagicMock(id=2)
    nb.dcim.device_roles.get.return_value = MagicMock(id=3)
    nb.dcim.devices.get.return_value = None
    created = MagicMock(id=99)
    nb.dcim.devices.create.return_value = created

    device = client.create_or_update_device(
        nb, "zcu102-lab1", carrier="zcu102", site_slug="lab1", custom_fields={"carrier": "zcu102"}
    )

    assert device is created
    nb.dcim.devices.create.assert_called_once_with(
        name="zcu102-lab1",
        device_type=2,
        role=3,
        site=1,
        custom_fields={"carrier": "zcu102"},
    )


def test_create_or_update_device_updates_when_present():
    nb = MagicMock()
    nb.dcim.sites.get.return_value = MagicMock(id=1)
    nb.dcim.device_types.get.return_value = MagicMock(id=2)
    nb.dcim.device_roles.get.return_value = MagicMock(id=3)
    existing = MagicMock()
    existing.custom_fields = {"carrier": "old"}
    nb.dcim.devices.get.return_value = existing

    device = client.create_or_update_device(
        nb, "zcu102-lab1", carrier="zcu102", site_slug="lab1", custom_fields={"carrier": "zcu102"}
    )

    assert device is existing
    existing.save.assert_called_once()
    assert existing.custom_fields["carrier"] == "zcu102"
    nb.dcim.devices.create.assert_not_called()


# NetBox 4.5+ rejects an Authorization header that isn't exactly two words
# ("Bearer nbt_<key>.<token>" / "Token <token>"); pynetbox adds the keyword
# itself, so the token must be the bare value.


@pytest.mark.parametrize(
    "raw",
    [
        "nbt_abc123.s3cret",
        "  nbt_abc123.s3cret\n",
        "Bearer nbt_abc123.s3cret",  # the header value, as shown in NetBox's docs
        "bearer  nbt_abc123.s3cret",
        "Authorization: Bearer nbt_abc123.s3cret",
        '"nbt_abc123.s3cret"',
    ],
)
def test_clean_token_leaves_the_bare_v2_token(raw):
    assert client.clean_token(raw) == "nbt_abc123.s3cret"


@pytest.mark.parametrize("raw", ["0123456789abcdef0123456789abcdef01234567", "Token 0123abcd"])
def test_clean_token_leaves_the_bare_v1_token(raw):
    assert client.clean_token(raw) == raw.removeprefix("Token ")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("nbt_abc123 s3cret", "space"),
        ("nbt_abc123", "only the key"),  # NetBox: "Could not parse key from v2 token"
        ("Bearer", "empty"),
        ("", "empty"),
    ],
)
def test_clean_token_rejects_what_netbox_cannot_parse(raw, message):
    with pytest.raises(ValueError, match=message):
        client.clean_token(raw)


def test_a_malformed_authorization_header_gets_a_token_format_hint():
    import pynetbox

    class _Forbidden:
        status_code, reason, url, text = 403, "Forbidden", "https://nb/api/", ""
        request = type("R", (), {"body": None})()

        def json(self):
            return {
                "detail": 'Invalid authorization header: Must be in the form "Bearer <key>.<token>"'
                ' or "Token <token>"'
            }

    with pytest.raises(RuntimeError) as e, client.reported_errors("https://nb"):
        raise pynetbox.RequestError(_Forbidden())

    assert "nbt_<key>.<token>" in str(e.value)
    assert "without the Bearer/Token keyword" in str(e.value)
