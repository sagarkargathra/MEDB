Troubleshooting
===============

SQLite Error: no column named shape
------------------------------------

Cause:
The API returned a new field not present in the existing table schema.

Resolution:
Schema alignment runs automatically before insertion.
If the error persists:

- delete the existing SQLite file
- rebuild the archive

No such table
-------------

Check table names:

.. code-block:: python

   get_archive_status(db_path)

Ensure the reporting function references the correct table.
