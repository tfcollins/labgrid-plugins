Drivers API
===========

Drivers provide low-level hardware control and protocol implementations.

**On this page:**

- `Power Drivers`_ — `VesyncPowerDriver`_, `CyberPowerDriver`_, `CyberPowerPdu`_, `HomeAssistantPowerDriver`_, `HomeAssistantClient`_
- `Shell and File Transfer`_ — `ADIShellDriver`_
- `Storage Drivers`_ — `MassStorageDriver`_
- `Kuiper Drivers`_ — `KuiperDLDriver`_
- `Cloudsmith Drivers`_ — `CloudsmithDLDriver`_
- `FPGA/JTAG Drivers`_ — `XilinxJTAGDriver`_
- `Network Drivers`_ — `TFTPServerDriver`_, `Utility Classes`_
- `Software Installer`_ — `SoftwareInstallerDriver`_

Power Drivers
-------------

VesyncPowerDriver
~~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.vesyncdriver.VesyncPowerDriver
   :members:
   :undoc-members:
   :show-inheritance:

CyberPowerDriver
~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.cyberpowerdriver.CyberPowerDriver
   :members:
   :undoc-members:
   :show-inheritance:

CyberPowerPdu
~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.cyberpowerdriver.CyberPowerPdu
   :members:
   :undoc-members:
   :show-inheritance:

HomeAssistantPowerDriver
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.homeassistantdriver.HomeAssistantPowerDriver
   :members:
   :undoc-members:
   :show-inheritance:

HomeAssistantClient
~~~~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.homeassistantdriver.HomeAssistantClient
   :members:
   :undoc-members:
   :show-inheritance:

Shell and File Transfer
------------------------

ADIShellDriver
~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.shelldriver.ADIShellDriver
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Storage Drivers
---------------

MassStorageDriver
~~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.massstoragedriver.MassStorageDriver
   :members:
   :undoc-members:
   :show-inheritance:

Kuiper Drivers
--------------

KuiperDLDriver
~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.kuiperdldriver.KuiperDLDriver
   :members:
   :undoc-members:
   :show-inheritance:

Cloudsmith Drivers
------------------

CloudsmithDLDriver
~~~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.cloudsmithdldriver.CloudsmithDLDriver
   :members:
   :undoc-members:
   :show-inheritance:

FPGA/JTAG Drivers
-----------------

XilinxJTAGDriver
~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.xilinxjtagdriver.XilinxJTAGDriver
   :members:
   :undoc-members:
   :show-inheritance:

Network Drivers
---------------

TFTPServerDriver
~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.tftpserverdriver.TFTPServerDriver
   :members:
   :undoc-members:
   :show-inheritance:

Utility Classes
~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.kuiperdldriver.Downloader
   :members:
   :undoc-members:

.. autoclass:: adi_lg_plugins.drivers.imageextractor.IMGFileExtractor
   :members:
   :undoc-members:

.. autoclass:: adi_lg_plugins.drivers.cloudsmithdldriver.Downloader
   :members:
   :undoc-members:

.. autofunction:: adi_lg_plugins.drivers.cloudsmithdldriver.get_latest_bootfiles

.. autofunction:: adi_lg_plugins.drivers.cloudsmithdldriver.parse_version_info

Software Installer
------------------

SoftwareInstallerDriver
~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: adi_lg_plugins.drivers.softwareinstaller.SoftwareInstallerDriver
   :members:
   :undoc-members:
   :show-inheritance:
