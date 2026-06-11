from pathlib import Path
import sys

project = "Mineral Extraction Database"
author = "Sagar Kargathra, Anish Koyamparambath"
release = "1.0.0"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    'sphinx_rtd_theme'
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

master_doc = "index"

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
