# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# -- Path setup --------------------------------------------------------------

# Add project source to path for autodoc
sys.path.insert(0, os.path.abspath("../../"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "adi-labgrid-plugins"
copyright = "2024, Analog Devices, Inc."
author = "Analog Devices, Inc."
version = "0.1.0"
release = "0.1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # Auto-generate API docs from docstrings
    "sphinx.ext.napoleon",  # Support for Google/NumPy style docstrings
    "sphinx.ext.viewcode",  # Add links to highlighted source code
    "sphinx.ext.intersphinx",  # Link to other project docs
    "sphinx.ext.autosummary",  # Generate summary tables
    "sphinx.ext.todo",  # Support for todo items
    "sphinx_copybutton",  # Add copy button to code blocks
    "sphinx_design",  # Better UI components (cards, tabs, etc.)
]

# -- Napoleon settings -------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None
napoleon_attr_annotations = True

# -- Autodoc settings --------------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}
autodoc_typehints = "description"
autodoc_mock_imports = [
    "pyvesync",
    "pytsk3",
    "pysnmp",
    "xmodem",
    "pylibiio",
    "iio",
    "pexpect",
]

# -- Autosummary settings ----------------------------------------------------

autosummary_generate = True

# -- Intersphinx settings ----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "labgrid": ("https://labgrid.readthedocs.io/en/latest/", None),
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

templates_path = ["_templates"]
source_suffix = ".rst"
master_doc = "index"
language = "en"
exclude_patterns = []
pygments_style = "sphinx"

html_theme = "furo"
html_title = "adi-labgrid-plugins"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

# -- Furo theme options ------------------------------------------------------
# https://pradyunsg.me/furo/

html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "top_of_page_button": "edit",
    "source_repository": "https://github.com/analogdevicesinc/adi-labgrid-plugins",
    "source_branch": "main",
    "source_directory": "docs/source/",
}

# -- Todo extension settings -------------------------------------------------

todo_include_todos = True
