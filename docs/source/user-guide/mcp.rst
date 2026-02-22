Model Context Protocol (MCP) Server
====================================

The ``adi-labgrid-plugins`` package includes a Model Context Protocol (MCP) server implementation using ``fastmcp``. This allows Large Language Models (LLMs) to directly interact with your Labgrid-managed hardware through a standardized interface.

The MCP server provides:
- **Stateful Sessions**: Persistent Labgrid environments across multiple tool calls.
- **Real-time Feedback**: Detailed progress logging during long-running boot operations.
- **Standardized Tools**: A common interface for booting, shell access, and file transfers.

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

By default, the server runs using the Stdio transport, which is compatible with most MCP clients.

Client Examples
---------------

Claude Desktop
~~~~~~~~~~~~~~

To use the ADI Labgrid plugins with the Claude Desktop app, add the following to your ``claude_desktop_config.json`` (typically located in ``~/Library/Application Support/Claude/claude_desktop_config.json`` on macOS or ``%APPDATA%/Claude/claude_desktop_config.json`` on Windows):

.. code-block:: json

    {
      "mcpServers": {
        "adi-labgrid": {
          "command": "adi-lg-mcp"
        }
      }
    }

Claude Code
~~~~~~~~~~~

`Claude Code <https://docs.anthropic.com/en/docs/agents-and-tools/claude-code>`_ is a CLI agent that can use MCP servers. You can add the ADI Labgrid MCP server to Claude Code using the following command:

.. code-block:: bash

    claude mcp add adi-labgrid adi-lg-mcp

Once added, you can ask Claude to perform hardware tasks:

.. code-block:: text

    "Use Labgrid to boot the board in config.yaml and then tell me the kernel version."

Gemini CLI
~~~~~~~~~~

The Gemini CLI agent can also utilize MCP servers. Configuration is typically handled via a settings file (e.g., ``.gemini/settings.json`` in your project or home directory):

.. code-block:: json

    {
      "mcpServers": {
        "adi-labgrid": {
          "command": "adi-lg-mcp"
        }
      }
    }

You can then interact with the agent:

.. code-block:: bash

    gemini "Boot the VPK180 board using config_ad9084_vpk180.yaml and run dmesg."

Exposed Tools
-------------

The MCP server exposes several tools for hardware management. All boot tools return a ``session_id`` which must be used for subsequent shell or SSH commands to maintain the same environment.

Boot Tools
~~~~~~~~~~

boot_fabric
^^^^^^^^^^^
Executes the JTAG-based ``BootFabric`` strategy.

- **Arguments:**
    - ``config_path`` (string, required): Path to the Labgrid configuration.
    - ``bitstream_path`` (string, optional): Path to override the bitstream file.
    - ``kernel_path`` (string, optional): Path to override the kernel image.
    - ``target`` (string, default: "main"): Labgrid target name.
    - ``state`` (string, default: "shell"): Desired transition state.
    - ``session_id`` (string, optional): Reuse an existing session.

boot_soc
^^^^^^^^
Executes the SD Mux-based ``BootFPGASoC`` strategy.

- **Arguments:**
    - ``config_path`` (string, required): Labgrid configuration path.
    - ``release_version`` (string, optional): Kuiper release version.
    - ``update_image`` (boolean, default: false): Flash full SD image.
    - ... (other paths and overrides)

boot_soc_ssh
^^^^^^^^^^^^
Executes the ``BootFPGASoCSSH`` strategy. Uses SSH for file transfers instead of SD Mux.

boot_selmap
^^^^^^^^^^^
Executes the ``BootSelMap`` strategy for dual-FPGA systems.

boot_soc_tftp
^^^^^^^^^^^^^
Executes the ``BootFPGASoCTFTP`` strategy. Loads the kernel via TFTP.

- **Arguments:**
    - ``config_path`` (string, required): Labgrid configuration path.
    - ``tftp_root`` (string, optional): Override TFTP root directory.
    - ``kernel_path`` (string, optional): Override kernel image path.
    - ``dtb_path`` (string, optional): Override device tree path.
    - ``release_version`` (string, optional): Kuiper release version.
    - ``target`` (string, default: "main"): Labgrid target name.
    - ``state`` (string, default: "shell"): Desired transition state.
    - ``session_id`` (string, optional): Reuse an existing session.

Provisioning Tools
~~~~~~~~~~~~~~~~~~

provision_software
^^^^^^^^^^^^^^^^^^
Executes the ``SoftwareProvisioningStrategy`` to automate software installation, builds, and testing.

- **Arguments:**
    - ``config_path`` (string, required): Labgrid configuration path.
    - ``packages`` (list[string], optional): List of package names to install.
    - ``repos`` (list[dict|list], optional): List of repositories to clone.
    - ``build_steps`` (list[dict|list], optional): List of build commands to run.
    - ``test_steps`` (list[dict|list], optional): List of test commands to run.
    - ``target`` (string, default: "main"): Labgrid target name.
    - ``state`` (string, default: "tested"): Desired transition state.
    - ``session_id`` (string, optional): Reuse an existing session.

Interaction Tools
~~~~~~~~~~~~~~~~~

run_shell_command
^^^^^^^^^^^^^^^^^
Run a command on the target via the serial console (requires an active session).

- **Arguments:**
    - ``session_id`` (string, required): The ID returned by a boot tool.
    - ``command`` (string, required): The shell command to execute.

run_ssh_command
^^^^^^^^^^^^^^^
Run a command on the target via SSH (requires an active session).

- **Arguments:**
    - ``session_id`` (string, required): The ID returned by a boot tool.
    - ``command`` (string, required): The command to execute.

Session Management
~~~~~~~~~~~~~~~~~~

list_sessions
^^^^^^^^^^^^^
List all active sessions and their associated metadata (config path, target, strategy).

get_session_info
^^^^^^^^^^^^^^^^
Get detailed information about a specific session by its ID.

Resources
---------

The MCP server exposes resources that allow clients to read session state directly.

labgrid://sessions
~~~~~~~~~~~~~~~~~~
Returns a JSON list of all active sessions, including metadata like target name, strategy, and config path.

labgrid://sessions/{session_id}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Returns detailed JSON information about a specific session identified by ``session_id``.

Logging and Progress
--------------------

The MCP server is configured to provide ``INFO`` level logging by default. When a long-running operation (like flashing a bitstream or writing an SD image) is in progress, the server emits progress logs to stderr, which are captured and displayed by most MCP-compatible CLI agents.

Example logs seen during execution:

.. code-block:: text

    INFO: Transitioning to Status.flash_fpga (Current: Status.powered_on)
    INFO: Initializing JTAG and flashing bitstream/kernel (this may take several minutes)...
    INFO: Bitstream flashed and kernel started via JTAG successfully
    INFO: Transitioning to Status.booted (Current: Status.flash_fpga)
    INFO: Waiting for Linux boot and 'login:' prompt...
    INFO: Microblaze kernel booted successfully