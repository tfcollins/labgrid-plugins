Configuration
=============

Target Configuration Basics
----------------------------

labgrid-plugins uses YAML files to configure targets, resources, and drivers.

.. tip::

    You can use the interactive configuration wizard to generate a valid configuration file automatically:

    .. code-block:: bash

        adi-lg generate-config

Basic Structure
~~~~~~~~~~~~~~~

.. tab-set::

    .. tab-item:: Exporter

        Exporter resource configuration (``resources.yaml``):

        .. code-block:: yaml

            target_name:
              ResourceType:
                cls: ResourceType
                parameter1: value1
                parameter2: value2

        Client environment configuration (``target.yaml``):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              target_name:
                resources:
                  RemotePlace:
                    name: target_name

                drivers:
                  DriverType: {}

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
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
