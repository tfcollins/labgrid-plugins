Exporter Deployment
===================

Deploy a ``labgrid-exporter`` process on a physical host so its hardware
becomes available through the coordinator.

This page covers the host-side plumbing: the ser2net version caveat,
the PATH the exporter needs, and how to run and verify it. For the
contents of the resource YAML itself, see :doc:`exporter-setup`.

Prerequisites
-------------

- Python 3.10 or newer on the exporter host
- SSH access to the host (for remote lifecycle management)
- Network reachability from the host to the coordinator gRPC port
  (default ``:20408``)
- A resource YAML describing the hardware attached to the host
  (see :doc:`exporter-setup`)

.. _ser2net-install:

Install ser2net 4.6.1
---------------------

.. warning::

   ``ser2net`` **4.6.0** (the version shipped in current Debian and
   Ubuntu packages) hangs on the RFC2217 ``purge`` option. Tests and
   clients reach the serial port, connect over TCP, and then time out
   with::

       serial.serialutil.SerialException: Could not open serial port
       rfc2217://<host>:<port>?ign_set_control&timeout=3.0:
       timeout while waiting for option 'purge'

   Install **4.6.1** or newer from source and put it first on PATH.

Download the source from the `ser2net releases page
<https://github.com/cminyard/ser2net/releases>`_ and build it into a
per-user prefix so it does not fight the system package:

.. code-block:: bash

   cd /tmp
   curl -LO https://github.com/cminyard/ser2net/archive/refs/tags/v4.6.1.tar.gz
   tar xzf v4.6.1.tar.gz
   cd ser2net-4.6.1
   ./configure --prefix=$HOME/opt/ser2net-4.6.1
   make -j
   make install

Verify:

.. code-block:: bash

   $HOME/opt/ser2net-4.6.1/sbin/ser2net -v
   # ser2net version 4.6.1

Install adi-labgrid-plugins
---------------------------

On the exporter host:

.. code-block:: bash

   git clone <repo-url>
   cd lg-coordinator
   pip install -e ".[dev]"

The ``dev`` extra pulls in ``labgrid`` itself (from the ADI fork) and
every resource class the exporter might be asked to publish.

Run the Exporter
----------------

Run ``labgrid-exporter`` with ``$HOME/opt/ser2net-4.6.1/sbin`` prepended
to ``PATH``. ``labgrid-exporter`` spawns ``ser2net`` per serial
resource by name, so the PATH order determines which binary handles
RFC2217 traffic.

Foreground (for smoke-testing):

.. code-block:: bash

   cd /path/to/exporter/yaml
   PATH="$HOME/opt/ser2net-4.6.1/sbin:$PATH" \
       labgrid-exporter \
           -c <coordinator-host>:20408 \
           -n <exporter-name> \
           resources.yaml

Daemonized:

.. code-block:: bash

   cd /path/to/exporter/yaml
   nohup env PATH="$HOME/opt/ser2net-4.6.1/sbin:$PATH" \
       labgrid-exporter \
           -c <coordinator-host>:20408 \
           -n <exporter-name> \
           resources.yaml \
       >/tmp/lg_exporter.log 2>&1 </dev/null &

Pick a unique ``-n <exporter-name>`` per host. Resources appear on the
coordinator under that prefix (``<exporter-name>/<group>/<cls>``).

Verify Registration
-------------------

From any host with ``labgrid-client`` installed:

.. code-block:: bash

   labgrid-client -x <coordinator-host>:20408 resources | grep '^<exporter-name>/'
   labgrid-client -x <coordinator-host>:20408 places

Resources should list every entry from the YAML. Places you have
already configured (see :doc:`exporter-setup`) should resolve.

To confirm the serial path end-to-end, acquire a place that uses this
exporter and open its console:

.. code-block:: bash

   labgrid-client -x <coordinator-host>:20408 -p <place> acquire
   labgrid-client -x <coordinator-host>:20408 -p <place> console
   # Ctrl-] to exit
   labgrid-client -x <coordinator-host>:20408 -p <place> release

Troubleshooting
---------------

``timeout while waiting for option 'purge'``
    The exporter spawned ``ser2net`` 4.6.0 instead of 4.6.1. Stop the
    exporter, confirm ``which ser2net`` resolves to the 4.6.1 install
    under the same PATH the exporter uses, and restart with that PATH.
    See :ref:`ser2net-install`.

``queued update for resource ...`` then no place on the coordinator
    The resources registered, but no place matches them. Create a
    place and add a match pattern — see the "Setting Up Places"
    section of :doc:`exporter-setup`.

Exporter exits with ``resource ... could not be opened``
    A serial device path in the resource YAML does not exist on the
    host. Prefer stable ``/dev/serial/by-id/...`` symlinks over
    ``/dev/ttyUSB*`` so USB re-enumeration does not break the config.
