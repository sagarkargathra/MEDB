Ingestion
=========

Purpose
-------

The ingestion process reads records from the BGS OGC API
and writes them into a local SQLite archive.

Entry Point
-----------

The main function is:

``build_master_database``

It performs:

- API pagination
- Batch aggregation
- Conversion to DataFrame
- Schema alignment
- SQLite insertion
- Index creation

Schema Alignment
----------------

Before appending new batches, the module checks
whether new columns exist in the API response.

If new fields are detected, missing columns are added
using ``ALTER TABLE``.

This prevents errors such as:

- no column named shape

Derived Columns
---------------

The field ``year_clean`` is derived from the first four
characters of the ``year`` column.
