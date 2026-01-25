Model Context Protocol (MCP) Server
====================================

The ``adi-labgrid-plugins`` package includes a Model Context Protocol (MCP) server implementation using ``fastmcp``. This allows LLMs (like Claude) to directly interact with your Labgrid-managed hardware through a standardized interface.

Installation
------------

The MCP server requires the ``fastmcp`` library. It is included in the base dependencies if installed with recent versions, or you can install it manually:

.. code-block:: bash

    pip install fastmcp

Running the Server
------------------

You can start the MCP server using the ``adi-lg-mcp`` command:

.. code-block:: bash

    adi-lg-mcp

By default, the server runs using the Stdio transport, which is compatible with MCP clients like the Claude Desktop app.

Configuration with Claude Desktop
---------------------------------

To use the ADI Labgrid plugins with Claude Desktop, add the following to your ``claude_desktop_config.json``:

.. code-block:: json

    {
      "mcpServers": {
        "adi-labgrid": {
          "command": "python",
          "args": [
            "-m",
            "adi_lg_plugins.tools.mcp"
          ],
          "env": {
            "PYTHONPATH": "/path/to/adi-labgrid-plugins"
          }
        }
      }
    }

Exposed Tools
-------------

The MCP server exposes the following tools to the LLM:

boot_fabric
~~~~~~~~~~~

Executes the ``BootFabric`` strategy.

* **Arguments:**
    * ``config_path`` (string, required): Path to the Labgrid configuration.
    * ``bitstream_path`` (string, optional): Path to a bitstream file.
    * ``kernel_path`` (string, optional): Path to a kernel image.
    * ``target`` (string, default: "main"): Labgrid target name.
    * ``state`` (string, default: "shell"): Desired state.

boot_soc
~~~~~~~~

Executes the ``BootFPGASoC`` strategy.

* **Arguments:**
    * ``config_path`` (string, required): Path to the Labgrid configuration.
    * ``release_version`` (string, optional): Kuiper release version.
    * ``kernel_path`` (string, optional): Path to a kernel file.
    * ``bootbin_path`` (string, optional): Path to a BOOT.BIN file.
    * ``devicetree_path`` (string, optional): Path to a devicetree file.
    * ``target`` (string, default: "main"): Labgrid target name.
    * ``state`` (string, default: "shell"): Desired state.
    * ``update_image`` (boolean, default: false): Flash full image.

boot_soc_ssh
~~~~~~~~~~~~

Executes the ``BootFPGASoCSSH`` strategy.

* **Arguments:** Similar to ``boot_soc``, but uses SSH for file transfer.

boot_selmap
~~~~~~~~~~~

Executes the ``BootSelMap`` strategy for dual-FPGA systems.

* **Arguments:**
    * ``config_path`` (string, required): Path to the Labgrid configuration.
    * ``pre_boot_files`` (object, optional): Mapping of local to remote paths for pre-boot files.
    * ``post_boot_files`` (object, optional): Mapping of local to remote paths for post-boot files.
    * ``target`` (string, default: "main"): Labgrid target name.
    * ``state`` (string, default: "shell"): Desired state.

Benefits of MCP
---------------

Using the MCP server allows an AI agent to:
1.  Understand the available hardware test capabilities.
2.  Automatically select the correct boot strategy based on the hardware description.
3.  Perform complex boot sequences and verify results autonomously.
4.  Integrate hardware testing into a larger AI-driven development workflow.
