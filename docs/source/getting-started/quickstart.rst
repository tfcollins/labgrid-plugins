Quick Start
===========

This guide will walk you through your first use of adi-labgrid-plugins.

Basic Power Control Example
----------------------------

Create a target configuration file:

.. code-block:: yaml

    # target.yaml
    targets:
      my_device:
        resources:
          VesyncOutlet:
            outlet_names: 'My Device Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 3.0

        drivers:
          VesyncPowerDriver: {}

Control the power from Python:

.. code-block:: python

    from labgrid import Environment

    # Load the environment
    env = Environment("target.yaml")
    target = env.get_target("my_device")

    # Get the power driver
    power = target.get_driver("VesyncPowerDriver")

    # Control power
    power.on()   # Turn on
    power.cycle()  # Power cycle
    power.off()  # Turn off

Next Steps
----------

- :doc:`configuration` - Learn more about configuration options
- :doc:`../user-guide/drivers` - Explore available drivers
- :doc:`../api/index` - Full API reference
