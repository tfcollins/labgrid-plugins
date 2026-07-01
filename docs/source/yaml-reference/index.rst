YAML Reference
==============

Quick schema lookup for every resource, driver, and strategy registered by
``labgrid-plugins``. Use this section as a cheat sheet when authoring a target
YAML; each component name links back to its full user-guide entry for prose and
troubleshooting.

.. grid:: 3

    .. grid-item-card:: Resources
        :link: resources
        :link-type: doc

        Hardware and network descriptors: outlets, storage, TFTP, JTAG.

    .. grid-item-card:: Drivers
        :link: drivers
        :link-type: doc

        Protocol implementations that bind to resources and expose Python APIs.

    .. grid-item-card:: Strategies
        :link: strategies
        :link-type: doc

        State-machine workflows that orchestrate boot and provisioning sequences.

.. toctree::
   :maxdepth: 2
   :hidden:

   resources
   drivers
   strategies
