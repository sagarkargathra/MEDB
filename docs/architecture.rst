Architecture
============

Overview
--------

The BGS module separates responsibilities into logical units:

- API client (HTTP communication)
- Extraction pipeline (API to DataFrame)
- Database layer (SQLite handling)
- Reporting layer (structured SQL queries)

Data Flow
---------

1. Call BGS OGC endpoint with pagination.
2. Extract ``features[*].properties``.
3. Convert to pandas DataFrame.
4. Derive ``year_clean``.
5. Append to SQLite archive.
6. Create indexes.
7. Provide read-only reporting queries.

Module Structure
----------------

``src/bgs/`` contains:

- ``config.py``
- ``client.py``
- ``db.py``
- ``extract.py``
- ``queries.py``
- ``reporting.py``

Each module isolates a specific responsibility.
