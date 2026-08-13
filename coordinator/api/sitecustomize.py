"""Container-side Python startup hook.

Two things happen at every Python startup inside the API container:

1. Register the ADI labgrid plugins, so plugin resource classes
   (KuiperRelease, VesyncOutlet, CyberPowerOutlet, HomeAssistantOutlet,
   ...) are known to target_factory. Importing ``adi_lg_plugins`` runs
   the ``@reg_driver``/``@reg_resource`` decorators for every plugin.
   Without this step, labgrid-client fails with 'unknown resource
   class' before any command runs. (Upstream labgrid has no
   entry-point plugin auto-discovery, so this explicit import is the
   registration trigger.)

2. Monkey-patch labgrid-client's `power` subcommand with a plugin-aware
   fallback. Upstream labgrid-client only knows how to bind
   PowerProtocol drivers for a hardcoded set of built-in resource
   classes (NetworkPowerPort, NetworkUSBPowerPort, etc.). For plugin
   resources, the original raises 'target has no compatible resource
   available'. The patch catches that and dispatches to the matching
   plugin driver based on the resource class name.
"""

# (1) Register the ADI plugins (import side effect registers all classes).
try:
    import adi_lg_plugins  # noqa: F401
except Exception:
    pass


# (2) labgrid-client power fallback for plugin resources
def _patch_labgrid_client_power():
    try:
        from labgrid.remote.client import ClientSession
    except Exception:
        return

    PLUGIN_RESOURCE_TO_DRIVER = {
        "APCOutlet": "APCDriver",
        "VesyncOutlet": "VesyncPowerDriver",
        "CyberPowerOutlet": "CyberPowerDriver",
        "HomeAssistantOutlet": "HomeAssistantPowerDriver",
    }

    orig_power = ClientSession.power

    def power(self):
        # Try the upstream behaviour first — handles all built-in cases.
        try:
            return orig_power(self)
        except Exception as e:
            msg = str(e)
            if "no compatible resource" not in msg:
                raise

        # Fallback: dispatch to a plugin driver based on resource class.
        place = self.get_acquired_place()
        target = self._get_target(place)
        action = self.args.action
        delay = self.args.delay
        name = self.args.name

        drv = None
        for resource in target.resources:
            if name and resource.name != name:
                continue
            cls_name = type(resource).__name__
            driver_name = PLUGIN_RESOURCE_TO_DRIVER.get(cls_name)
            if driver_name is None:
                continue
            drv = self._get_driver_or_new(target, driver_name, name=name)
            if drv:
                break

        if drv is None:
            from labgrid.remote.client import UserError

            raise UserError("target has no compatible resource available")

        if delay is not None:
            try:
                drv.delay = delay
            except AttributeError:
                pass
        result = getattr(drv, action)()
        if action == "get":
            print(
                f"power{' ' + name if name else ''} for place {place.name} is {'on' if result else 'off'}"
            )

    ClientSession.power = power


try:
    _patch_labgrid_client_power()
except Exception:
    pass
