# docs/conf.py
from __future__ import annotations

from pathlib import Path
import sys

# Project information
project = "World Mineral Archive"
author = "Anish Koyamparambath"
copyright = f"{author}"
release = "0.1.0"

# Ensure we can import src/bgs without packaging
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Extensions
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

# General config
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Autodoc
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"

# HTML output
html_theme = "alabaster"
html_static_path = ["_static"]

# Sphinx will generate a search index by default in HTML builds
html_use_index = True
html_search_language = "en"
