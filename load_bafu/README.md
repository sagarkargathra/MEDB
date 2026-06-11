# Load BAFU Workflow

This folder is the complete BAFU loading workflow. It replaces the old mapping
subpackage with one local utility file, one notebook, one editable mapping CSV,
and the BAFU EcoSpold XML folder.

## Folder contents

- `load bafu.ipynb`: documented notebook that runs the workflow.
- `utils.py`: parser, mapper, report writer, and Brightway loader used by the notebook.
- `flows.csv`: manual BAFU elementary-flow mapping table.
- `ecospold/`: BAFU EcoSpold XML files.
- `output/`: created by the notebook when mapping reports are written.

## Workflow

Use a notebook kernel or Python environment with `lxml`, `pandas`, `bw2data`,
`bw2io`, `openpyxl`, and `tqdm` installed. The system Python on some machines
will not have these packages; choose the Brightway environment instead.

1. Open `load bafu.ipynb`.
2. Review the configuration cell:
   - `PROJECT` is the Brightway project to use.
   - `BAFU_DB` is the BAFU database that will be written.
   - `ECOINVENT_DB` and `BIOSPHERE_DB` must match the installed ecoinvent
     release databases.
   - `VERSION` and `SYSTEM_MODEL` are used only if the notebook needs to import
     ecoinvent into the Brightway project.
3. Run the setup and input-check cells.
4. Run the load cell. This parses every XML file in `ecospold/` into
   Brightway-compatible dataset dictionaries.
5. Run the mapping cell. This applies `flows.csv`, checks mapped targets
   against the selected ecoinvent biosphere, and writes:
   - `output/biosphere_mapping_audit.csv`
   - `output/unmapped_flows_report.csv`
   - `output/summary.csv`
6. Review `output/unmapped_flows_report.csv`.
7. Update `flows.csv` for any missing or incorrect elementary-flow decisions.
8. Rerun the notebook from the load cell.
9. Run the write cell when the audit looks acceptable. Unresolved BAFU-specific
   elementary flows are preserved in a separate Brightway database named
   `bafu biosphere`.

## Mapping CSV format

`flows.csv` is semicolon-delimited and uses these columns:

- `BAFU name`
- `BAFU category`
- `Ecoinvent name`
- `Ecoinvent category`

Categories are written as Python tuples, for example:

```text
('water', 'surface water')
```

Leave the ecoinvent columns blank only when the BAFU flow should remain
unmapped and be preserved in `bafu biosphere`.

## Mapping Change Log

Paste the mapping-change log below this section when it is ready. Keep one row
or bullet per mapping decision, with the BAFU flow, chosen ecoinvent flow, and
reason for the decision.
