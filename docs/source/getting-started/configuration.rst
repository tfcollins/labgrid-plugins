Configuration
=============

Target Configuration Basics
----------------------------

adi-labgrid-plugins uses YAML files to configure targets, resources, and drivers.

Basic Structure
~~~~~~~~~~~~~~~

.. code-block:: yaml

    targets:
      target_name:
        resources:
          ResourceType:
            parameter1: value1
            parameter2: value2

        drivers:
          DriverType: {}

Resource Configuration
----------------------

See :doc:`../api/resources` for complete documentation of all available resources.

Driver Configuration
--------------------

See :doc:`../api/drivers` for complete documentation of all available drivers.

Example Configurations
----------------------

Complete example configuration files are available in the ``examples/target_examples/`` directory:

- ``simple_power.yaml`` - Basic power control
- ``boot_fpga_soc.yaml`` - Complete FPGA SoC boot
- ``selmap_boot.yaml`` - Dual FPGA boot

See Also
--------

- :doc:`../user-guide/resources` - Resource configuration guide
- :doc:`../user-guide/drivers` - Driver usage guide
- :doc:`../user-guide/strategies` - Strategy configuration
