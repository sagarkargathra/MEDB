World Mineral Archive
=====================

This documentation describes the BGS ingestion and reporting module.
The module builds a local SQLite archive from the BGS World Mineral
Statistics OGC API and provides structured query utilities.

The project currently supports:

- BGS ingestion (API to SQLite)
- Local archive management
- Commodity-specific reporting queries

Future extension:

- USGS ingestion
- Full packaging

.. toctree::
   :maxdepth: 2
   :caption: Contents

   installation
   architecture
   ingestion
   reporting
   data_model
   cli
   api_reference
   troubleshooting
   licensing
