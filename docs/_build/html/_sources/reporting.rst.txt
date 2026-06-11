Reporting
=========

Purpose
-------

The reporting layer provides structured queries
that return analysis-ready DataFrames.

Design Principles
-----------------

- Read-only access to SQLite
- No database mutation
- Explicit SQL
- Deterministic column renaming

Core Functions
--------------

``get_archive_status``
    Returns all tables with row counts.

``get_table_columns``
    Returns schema information for a table.

``inspect_commodity_year_raw``
    Returns raw rows filtered by commodity and year.

``get_clean_production_report``
    Returns a structured production dataset with renamed columns.

Example
-------

.. code-block:: python

   df = get_clean_production_report(
       db_path,
       commodity_like="Lithium",
       table="FullMineralData",
   )
