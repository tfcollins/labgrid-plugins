YAML Reference
==============

Quick schema lookup for every resource, driver, and strategy registered by
``labgrid-plugins``. Use this section when authoring a target YAML. Each argument
entry states whether it is required, shows its implementation default, explains
what behavior it controls, and gives a representative value. The complete YAML
beneath each component demonstrates where that value belongs in a real environment.

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
