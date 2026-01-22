adi-labgrid-plugins Documentation
==================================

**adi-labgrid-plugins** is a labgrid plugin package providing Analog Devices specific drivers, resources, and strategies for automated testing and device control of FPGA SoC systems.

.. grid:: 2

    .. grid-item-card:: Getting Started
        :link: getting-started/index
        :link-type: doc

        New to adi-labgrid-plugins? Start here with installation and basic usage.

    .. grid-item-card:: API Reference
        :link: api/index
        :link-type: doc

        Complete API documentation for all components.

    .. grid-item-card:: User Guide
        :link: user-guide/index
        :link-type: doc

        Learn how to configure and use drivers, resources, and strategies.

    .. grid-item-card:: Developer Guide
        :link: developer-guide/index
        :link-type: doc

        Contributing, architecture, and implementation patterns.

.. admonition:: Version Information
    :class: note

    Current version: **0.1.0** (early development)

    This is early-stage software under active development. Expect incomplete features and ongoing architectural changes.

Features
--------

- **Power Control**: VeSync smart outlets and CyberPower PDU support
- **Shell Access**: XMODEM file transfer over serial console
- **Boot Strategies**: Automated FPGA SoC boot with kernel replacement
- **Mass Storage**: SD card file management via USB mux
- **Kuiper Linux**: Download and manage ADI Kuiper releases

Quick Example
-------------

.. code-block:: yaml

    # target.yaml
    targets:
      my_device:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'user@example.com'
            password: 'password'

        drivers:
          VesyncPowerDriver: {}

.. code-block:: python

    # Control device power
    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("my_device")
    power = target.get_driver("VesyncPowerDriver")

    power.on()   # Turn on device
    power.off()  # Turn off device

.. toctree::
   :maxdepth: 2
   :caption: Contents:
   :hidden:

   getting-started/index
   user-guide/index
   api/index
   developer-guide/index
   examples/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
