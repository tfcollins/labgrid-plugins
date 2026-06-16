import os

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


def _optional_str_or_str_iterable(inst, attr, value):
    """Validate that ``value`` is None, a str, or a list/tuple of str.

    Lets the search-filter fields (``vfilter``/``vnot``) accept either a
    single term (back-compat for YAML/programmatic use) or several terms.
    """
    if value is None or isinstance(value, str):
        return
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return
    raise TypeError(f"'{attr.name}' must be None, a str, or a list/tuple of str (got {value!r})")


@target_factory.reg_resource
@attr.s(eq=False)
class CloudsmithRelease(Resource):
    """The CloudsmithRelease describes a Cloudsmith-hosted boot artifact.

    The driver resolves a package from a Cloudsmith package repo (default
    ``adi/sdg-boot-partition``) by full-text search on the filename plus
    the FPGA carrier and daughter card, then downloads the matching file
    (e.g. ``BOOT.BIN``). By default the *latest* matching package is used;
    set ``version`` to pin an exact package version for reproducibility.

    Args:
        fpga_carrier (str): Optional short FPGA carrier name, e.g. ``zcu102``.
        daughter_card (str): Optional daughter card / chip, e.g. ``adrv9009``.
        vfilter (str | list[str]): Optional filter term(s) to narrow the
            search. A single string or a list/tuple of strings; each term
            adds an ``AND version:*term*`` clause to the query.
        vnot (str | list[str]): Optional term(s) to exclude from the search.
            A single string or a list/tuple of strings; each term adds an
            ``AND version:~term`` clause to the query.
        owner (str): Cloudsmith owner/org. Defaults to ``adi``.
        repo (str): Cloudsmith repository. Defaults to ``sdg-boot-partition``.
        filename (str): Artifact filename to resolve. Defaults to ``BOOT.BIN``.
        version (str): Optional exact package version to pin. If None, the
            latest matching package is resolved.
        api_token (str): Cloudsmith API token. Defaults to the
            ``CLOUDSMITH_API_TOKEN`` environment variable.
        cache_path (str): Path to cache downloaded artifacts. Defaults to
            ``~/.labgrid/cloudsmith_releases/``.
        boot_file_path (str): Resolved local path to the downloaded file.
            Set by the driver after download; not a constructor argument.
    """

    fpga_carrier = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    daughter_card = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    vfilter = attr.ib(default=None, validator=_optional_str_or_str_iterable)
    vnot = attr.ib(default=None, validator=_optional_str_or_str_iterable)

    owner = attr.ib(default="adi", validator=attr.validators.instance_of(str))
    repo = attr.ib(default="sdg-boot-partition", validator=attr.validators.instance_of(str))
    filename = attr.ib(default="BOOT.BIN", validator=attr.validators.instance_of(str))
    version = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    api_token = attr.ib(
        default=attr.Factory(lambda: os.environ.get("CLOUDSMITH_API_TOKEN")),
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    cache_path = attr.ib(
        default="~/.labgrid/cloudsmith_releases/",
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    boot_file_path = attr.ib(
        default=None,
        init=False,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
