Legacy CI (Deprecated)
======================

.. deprecated:: v3
   The workflows described here (``hw-matrix.yml``, ``hw-matrix-v2.yml``) are deprecated. New consumer repositories should use the :doc:`hw-request` family.

Historical reference documentation for older matrix discovery and bash test flows:

.. grid:: 1 2 2 3
   :gutter: 3
   :class-container: sd-mb-4

   .. grid-item-card:: Hardware CI v1
      :link: hardware-ci
      :link-type: doc

      Manifest-first hardware CI workflow (``hw-matrix.yml``).

   .. grid-item-card:: Hardware CI v2
      :link: hw-ci-v2
      :link-type: doc

      Discovery-driven hardware CI workflow (``hw-matrix-v2.yml``).

   .. grid-item-card:: Bash Driver CI
      :link: hw-ci-bash
      :link-type: doc

      Hardware CI flow for UART and JTAG tests driven by bash scripts.

.. toctree::
   :maxdepth: 1
   :hidden:

   hardware-ci
   hw-ci-v2
   hw-ci-bash
