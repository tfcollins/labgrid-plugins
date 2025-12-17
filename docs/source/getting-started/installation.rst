Installation
============

Prerequisites
-------------

**Required**:

- Python >= 3.10
- labgrid (custom fork with plugin support)

**Optional Dependencies**:

- ``pyvesync``: For VeSync smart outlet control
- ``pysnmp``: For CyberPower PDU control
- ``pytsk3``: For disk image file extraction
- ``pylibiio``: For IIO device testing

Using pip
---------

Basic installation::

    pip install git+https://github.com/analogdevicesinc/adi-labgrid-plugins.git

Development installation::

    git clone https://github.com/analogdevicesinc/adi-labgrid-plugins.git
    cd adi-labgrid-plugins
    pip install -e ".[dev]"

Using uv (Recommended for Development)
---------------------------------------

`uv <https://github.com/astral-sh/uv>`_ is a fast Python package installer.

Create virtual environment::

    uv venv venv --python 3.10
    source venv/bin/activate

Install in editable mode with dev dependencies::

    uv pip install -e ".[dev]"

Building Documentation
----------------------

Install documentation dependencies::

    pip install -e ".[docs]"

Build HTML documentation::

    cd docs
    make html

View documentation::

    # Linux/Mac
    open build/html/index.html

    # Or use Python's HTTP server
    cd build/html
    python -m http.server 8000

The documentation will be available at http://localhost:8000

Verifying Installation
----------------------

Check that plugins are registered::

    python -c "import adi_lg_plugins; print('Installation successful!')"

List available drivers::

    python -c "from labgrid.factory import target_factory; print([k for k in target_factory.drivers.keys() if 'vesync' in k.lower() or 'cyberpower' in k.lower() or 'kuiper' in k.lower()])"

You should see drivers like ``VesyncPowerDriver``, ``ADIShellDriver``, ``CyberPowerDriver``, etc.

Next Steps
----------

- :doc:`quickstart` - Run your first test
- :doc:`configuration` - Learn about target configuration
- :doc:`../api/index` - Browse the API reference
