Data Model
==========

Source Structure
----------------

The BGS API returns:

- features
    - properties

Each ``properties`` dictionary becomes one row
in the SQLite table.

SQLite Archive
--------------

Default table:

- FullMineralData

Common fields include:

- year
- year_clean
- bgs_commodity_trans
- bgs_statistic_type_trans
- country_trans
- quantity
- units

Indexes
-------

Indexes are created on:

- erml_group
- year_clean

These support commodity and time filtering.
