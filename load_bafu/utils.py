"""Load mapped BAFU EcoSpold XML files into a Brightway project."""

from __future__ import annotations

import ast
import copy
import csv
import html
import importlib
import json
import logging
import math
import re
import sys
import uuid
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from lxml import etree

T = TypeVar("T")

UNDEF = 0
LOGNORM = 2
NORMAL = 3
UNIFORM = 4
TRIANGULAR = 5

BAFU_BIOSPHERE = "bafu biosphere"
BAFU_NAMESPACE = "https://github.com/BAFU4WeLOOP/bafu-biosphere"

NAME_LOC_RE = re.compile(r"^(.*)\s+\{([^{}]+)\}\s*$")
TAG_RE = re.compile(r"<[^>]+>")
PROCESS_RE = re.compile(
    r"^process_([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.xml$"
)

UNIT_ROWS = (
    ("Bq", "Becquerel"),
    ("MJ", "megajoule"),
    ("Nm3", "cubic meter"),
    ("a", "year"),
    ("ha", "hectare"),
    ("hr", "hour"),
    ("kBq", "kilo Becquerel"),
    ("kWh", "kilowatt hour"),
    ("kg", "kilogram"),
    ("km", "kilometer"),
    ("kmy", "kilometer-year"),
    ("m", "meter"),
    ("m2", "square meter"),
    ("m2a", "square meter-year"),
    ("m3", "cubic meter"),
    ("m3y", "cubic meter-year"),
    ("my", "meter-year"),
    ("p", "unit"),
    ("personkm", "person-kilometer"),
    ("tkm", "ton kilometer"),
    ("unit", "unit"),
)

CAT_ROWS = (
    (("emissions to air", "unspecified"), ("air",)),
    (("emissions to air", "high. pop."), ("air", "urban air close to ground")),
    (
        ("emissions to air", "low. pop."),
        ("air", "non-urban air or from high stacks"),
    ),
    (
        ("emissions to air", "stratosphere + troposphere"),
        ("air", "lower stratosphere + upper troposphere"),
    ),
    (
        ("emissions to air", "low. pop., long-term"),
        ("air", "low population density, long-term"),
    ),
    (("emissions to air", "indoor"), ("air", "urban air close to ground")),
    (("emissions to soil", "unspecified"), ("soil",)),
    (("emissions to soil", "forestry"), ("soil", "forestry")),
    (("emissions to soil", "agricultural"), ("soil", "agricultural")),
    (("emissions to soil", "industrial"), ("soil", "industrial")),
    (("emissions to water", "ocean"), ("water", "ocean")),
    (("emissions to water", "river"), ("water", "surface water")),
    (("emissions to water", "unspecified"), ("water",)),
    (
        ("emissions to water", "groundwater, long-term"),
        ("water", "ground-, long-term"),
    ),
    (("emissions to water", "groundwater"), ("water", "ground-")),
    (("emissions to water", "lake"), ("water", "surface water")),
    (("emissions to water", "river, long-term"), ("water", "surface water")),
    (("emissions to water", "fossilwater"), ("water", "fossil well")),
    (("economic issues", "unspecified"), ("economic", "primary production factor")),
    (("resources", "in ground"), ("natural resource", "in ground")),
    (("resources", "land"), ("natural resource", "land")),
    (("resources", "in water"), ("natural resource", "in water")),
    (("resources", "in air"), ("natural resource", "in air")),
    (("resources", "biotic"), ("natural resource", "biotic")),
)

UNITS = MappingProxyType(dict(UNIT_ROWS))
CATS = MappingProxyType(dict(CAT_ROWS))
UNSPEC = {"unspecified", "(unspecified)", "", None}


def progress(items: Iterable[T], text: str, total: int | None = None) -> Iterator[T]:
    """Yield items through tqdm when it is installed."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Progress text must be a non-empty string")
    try:
        from tqdm.auto import tqdm
    except ImportError:
        yield from items
        return
    yield from tqdm(items, desc=text, total=total, dynamic_ncols=True)


def status(label: str, message: str) -> None:
    """Print one compact status line."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Status label must be a non-empty string")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Status message must be a non-empty string")
    print(f"[{label.strip().upper()}] {message.strip()}", file=sys.stdout, flush=True)


class Config:
    """Normalize BAFU units and categories into Brightway-friendly values."""

    def __init__(self) -> None:
        """Create the embedded mapping configuration."""
        self.units = dict(UNITS)
        self.cats = dict(CATS)

    def unit(self, text: str | None) -> str | None:
        """Return the Brightway unit name for a raw BAFU unit."""
        if text is None:
            return None
        if not isinstance(text, str):
            raise TypeError("Unit must be a string or None")
        raw = text.strip()
        if not raw:
            return None
        return str(self.units.get(raw, raw))

    def cat(self, raw: str | None, sub: str | None) -> tuple[str, ...] | None:
        """Return normalized categories for a raw BAFU category pair."""
        if raw is not None and not isinstance(raw, str):
            raise TypeError("Category must be a string or None")
        if sub is not None and not isinstance(sub, str):
            raise TypeError("Subcategory must be a string or None")
        pair = (raw or "", sub or "")
        return self.normcat(self.cats.get(pair, pair))

    def hascat(self, raw: str | None, sub: str | None) -> bool:
        """Return whether a raw category pair is a known elementary-flow category."""
        if raw is not None and not isinstance(raw, str):
            raise TypeError("Category must be a string or None")
        if sub is not None and not isinstance(sub, str):
            raise TypeError("Subcategory must be a string or None")
        return (raw or "", sub or "") in self.cats

    def parsecat(self, text: str | None) -> tuple[str, ...] | None:
        """Parse a CSV category tuple into normalized categories."""
        raw = (text or "").strip()
        if not raw:
            return None
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Invalid category tuple: {text}") from exc
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"Category value must be a tuple or list: {text}")
        return self.normcat(value)

    def normcat(self, cat: Iterable[str] | None) -> tuple[str, ...] | None:
        """Normalize a category sequence and remove unspecified tails."""
        if not cat:
            return None
        out = tuple(str(item).strip() for item in cat if item is not None)
        while out and out[-1] in UNSPEC:
            out = out[:-1]
        return out or None


class Xml:
    """Parse BAFU EcoSpold XML into Brightway dataset dictionaries."""

    def __init__(self, folder: str | Path, config: Config | None = None) -> None:
        """Create an XML parser for one EcoSpold folder."""
        self.folder = self._folder(folder)
        self.config = config or Config()
        self.data: list[dict[str, Any]] = []
        self.ref: dict[str, dict[str, Any]] = {}
        self.stat: dict[str, int] = {}

    def load(self, database: str) -> list[dict[str, Any]]:
        """Parse every XML file in the configured folder."""
        if not isinstance(database, str) or not database.strip():
            raise ValueError("Database name must be a non-empty string")
        files = sorted(self.folder.rglob("*.xml"))
        if not files:
            raise FileNotFoundError(f"No EcoSpold XML files found in {self.folder}")
        self.ref = self._buildref(files)
        self.data = []
        total = 0
        for file in progress(files, "Parsing BAFU EcoSpold XML", len(files)):
            item = self._parse(file, database.strip())
            if item is None:
                continue
            self.data.append(item)
            total += len(item.get("exchanges", []))
        self.stat = {"datasets": len(self.data), "exchanges": total}
        return self.data

    def _folder(self, value: str | Path) -> Path:
        if not isinstance(value, (str, Path)):
            raise TypeError("XML folder must be a string or Path")
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"XML folder not found: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"XML path is not a folder: {path}")
        return path

    def _buildref(self, files: list[Path]) -> dict[str, dict[str, Any]]:
        ref: dict[str, dict[str, Any]] = {}
        for file in progress(files, "Indexing BAFU references", len(files)):
            root = etree.parse(str(file)).getroot()
            dataset = self._first(root, '//*[local-name()="dataset"]')
            if dataset is None:
                continue
            info = self._first(dataset, './/*[local-name()="processInformation"]')
            func = self._first(info, './/*[local-name()="referenceFunction"]')
            geo = self._first(info, './/*[local-name()="geography"]')
            if func is None:
                continue
            name, loc = self._striploc(
                self._attr(func, "name", ""), self._attr(geo, "location", "GLO")
            )
            code = self._activitycode(file)
            source = self._attr(dataset, "number")
            flow = None
            data = self._first(dataset, './/*[local-name()="flowData"]')
            if data is not None:
                for exchange in data.xpath('./*[local-name()="exchange"]'):
                    if self._og(exchange) == "0":
                        flow = self._attr(exchange, "number")
                        if flow:
                            break
            key = flow or source or code
            if key:
                ref[key] = {
                    "activity_code": code,
                    "source_activity_code": source,
                    "name": name,
                    "reference product": name,
                    "location": loc or "GLO",
                    "unit": self.config.unit(self._attr(func, "unit")),
                }
        return ref

    def _parse(self, file: Path, database: str) -> dict[str, Any] | None:
        root = etree.parse(str(file)).getroot()
        dataset = self._first(root, '//*[local-name()="dataset"]')
        if dataset is None:
            return None
        info = self._first(dataset, './/*[local-name()="processInformation"]')
        func = self._first(info, './/*[local-name()="referenceFunction"]')
        geo = self._first(info, './/*[local-name()="geography"]')
        span = self._first(info, './/*[local-name()="timePeriod"]')
        if func is None:
            return None
        name, loc = self._striploc(
            self._attr(func, "name", ""), self._attr(geo, "location", "GLO")
        )
        code = self._activitycode(file)
        flow = self._first(dataset, './/*[local-name()="flowData"]')
        exchanges = []
        if flow is not None:
            for source in flow.xpath('./*[local-name()="exchange"]'):
                mean = self._attr(source, "meanValue")
                if mean is None:
                    continue
                raw_name = self._attr(source, "name", "")
                item_name, item_loc = self._striploc(
                    raw_name, self._attr(source, "location")
                )
                raw_cat = self._attr(source, "category", "")
                raw_sub = self._attr(source, "subCategory", "")
                kind = self._kind(source, raw_cat, raw_sub)
                item: dict[str, Any] = {
                    "name": item_name,
                    "unit": self.config.unit(self._attr(source, "unit")),
                    "type": kind,
                    "categories": self.config.cat(raw_cat, raw_sub),
                }
                if kind != "biosphere" and item_loc:
                    item["location"] = item_loc
                comment = self._attr(source, "generalComment")
                if comment:
                    item["comment"] = self._clean(comment)
                number = self._attr(source, "number")
                if number:
                    item["flow"] = number
                    if kind in {"technosphere", "production"} and number in self.ref:
                        ref = self.ref[number]
                        item["reference product"] = ref["reference product"]
                        item["target code"] = ref["activity_code"]
                        item["input"] = (database, ref["activity_code"])
                        item.setdefault("location", ref["location"])
                self._uncertainty(source, item)
                exchanges.append(item)
        return {
            "database": database,
            "code": code,
            "activity uuid": code,
            "source activity number": self._attr(dataset, "number", ""),
            "name": name,
            "reference product": name,
            "location": loc or "GLO",
            "unit": self.config.unit(self._attr(func, "unit")),
            "comment": self._comment(dataset, func, geo, info, span),
            "classifications": self._classify(func),
            "exchanges": exchanges,
            "filename": file.name,
            "type": "process",
        }

    def _kind(self, exchange: Any, raw_cat: str, raw_sub: str) -> str:
        og = self._og(exchange)
        ig = self._ig(exchange)
        low = (raw_cat or "").lower()
        bio = (
            low.startswith("emissions to ")
            or low.startswith("emission to ")
            or low in {"emissions", "emission"}
            or "resource" in low
            or self.config.hascat(raw_cat, raw_sub)
        )
        if og == "0":
            return "production"
        if bio:
            return "biosphere"
        if ig is not None:
            return "technosphere"
        return "biosphere"

    def _uncertainty(self, exchange: Any, data: dict[str, Any]) -> None:
        try:
            kind = int(self._attr(exchange, "uncertaintyType", "0"))
        except ValueError:
            kind = 0
        mean = self._num(self._attr(exchange, "meanValue"))
        low = self._num(self._attr(exchange, "minValue"))
        high = self._num(self._attr(exchange, "maxValue"))
        sigma = self._num(self._attr(exchange, "standardDeviation95"))
        if kind == 1 and (math.isnan(sigma) or sigma in {0.0, 1.0}):
            kind = 0
        if kind == 1 and not math.isnan(mean) and mean != 0:
            data.update(
                {
                    "uncertainty type": LOGNORM,
                    "amount": float(mean),
                    "loc": math.log(abs(mean)),
                    "scale": math.log(math.sqrt(float(sigma))),
                    "negative": mean < 0,
                }
            )
            if math.isnan(data["scale"]):
                data["uncertainty type"] = UNDEF
                data["loc"] = data["amount"]
                data.pop("scale", None)
            return
        if kind == 2:
            data.update(
                {
                    "uncertainty type": NORMAL,
                    "amount": float(mean),
                    "loc": float(mean),
                    "scale": float(sigma) / 2.0,
                }
            )
            return
        if kind == 3:
            mode = self._num(self._attr(exchange, "mostLikelyValue"))
            data.update(
                {
                    "uncertainty type": TRIANGULAR,
                    "minimum": float(low),
                    "maximum": float(high),
                    "amount": float(mode if not math.isnan(mode) else mean),
                    "loc": float(mode if not math.isnan(mode) else mean),
                }
            )
            return
        if kind == 4:
            data.update(
                {
                    "uncertainty type": UNIFORM,
                    "amount": float(mean),
                    "minimum": float(low),
                    "maximum": float(high),
                }
            )
            return
        data.update({"uncertainty type": UNDEF, "amount": float(mean), "loc": mean})

    def _activitycode(self, file: Path) -> str:
        match = PROCESS_RE.match(file.name)
        if not match:
            raise ValueError(f"BAFU XML file must be named process_<uuid>.xml: {file}")
        return str(uuid.UUID(match.group(1)))

    def _classify(self, func: Any) -> list[tuple[str, str]]:
        cat = self._attr(func, "category")
        sub = self._attr(func, "subCategory")
        if not cat and not sub:
            return []
        return [("EcoSpold01Categories", f"{cat or ''}/{sub or ''}")]

    def _comment(self, dataset: Any, func: Any, geo: Any, info: Any, span: Any) -> str:
        parts = []
        note = self._attr(func, "generalComment", "")
        if note:
            parts.append(note)
        geo_text = self._attr(geo, "text", "")
        geo_loc = self._attr(geo, "location", "")
        if geo_text or geo_loc:
            detail = geo_loc if not geo_text else f"{geo_loc} - {geo_text}"
            parts.append(f"Geography: {detail}".strip())
        tech = self._first(info, './/*[local-name()="technology"]')
        tech_text = self._attr(tech, "text", "")
        if tech_text:
            parts.append(f"Technology: {tech_text}")
        span_text = self._attr(span, "text", "")
        if span_text:
            parts.append(f"Time period: {span_text}")
        start = self._text(self._first(span, './/*[local-name()="startDate"]'))
        end = self._text(self._first(span, './/*[local-name()="endDate"]'))
        if start or end:
            parts.append("Time period (data): " + " - ".join(x for x in (start, end) if x))
        meta = self._first(dataset, './/*[local-name()="modellingAndValidation"]')
        rep = self._first(meta, './/*[local-name()="representativeness"]')
        if rep is not None:
            shown = []
            for key, label in (
                ("productionVolume", "Production volume"),
                ("samplingProcedure", "Sampling"),
                ("extrapolations", "Extrapolations"),
                ("uncertaintyAdjustments", "Uncertainty adjustments"),
            ):
                value = self._attr(rep, key, "")
                if value and value.lower() not in {"na", "none", "<null>"}:
                    shown.append(f"{label}: {value}")
            if shown:
                parts.append("Representativeness: " + "; ".join(shown))
        return self._clean("\n".join(parts))

    def _clean(self, text: str) -> str:
        if not text:
            return ""
        out = html.unescape(text)
        out = TAG_RE.sub(" ", out)
        out = re.sub(r"UUID:.*$", "", out, flags=re.S)
        lines = [line.strip() for line in out.replace("\r\n", "\n").split("\n")]
        return "\n".join(line for line in lines if line)

    def _striploc(self, name: str, loc: str | None) -> tuple[str, str | None]:
        if not name:
            return name, loc
        match = NAME_LOC_RE.match(name)
        if not match:
            return name, loc
        base, found = match.groups()
        return base.strip(), found.strip() or loc

    def _num(self, text: str | None) -> float:
        if text is None:
            return float("nan")
        try:
            return float(str(text).strip())
        except (TypeError, ValueError):
            return float("nan")

    def _first(self, elem: Any, path: str) -> Any:
        if elem is None:
            return None
        out = elem.xpath(path)
        return out[0] if out else None

    def _attr(self, elem: Any, name: str, default: Any = None) -> Any:
        if elem is None:
            return default
        value = elem.get(name)
        return value if value is not None else default

    def _text(self, elem: Any) -> str:
        if elem is None or elem.text is None:
            return ""
        return elem.text.strip()

    def _og(self, exchange: Any) -> str | None:
        return self._text(self._first(exchange, './*[local-name()="outputGroup"]')) or None

    def _ig(self, exchange: Any) -> str | None:
        return self._text(self._first(exchange, './*[local-name()="inputGroup"]')) or None


class FlowMap:
    """Load and apply the manual BAFU-to-ecoinvent elementary-flow CSV."""

    def __init__(self, file: str | Path, config: Config | None = None) -> None:
        """Create a mapping table object."""
        self.file = self._file(file)
        self.config = config or Config()
        self.rules: dict[tuple[str, tuple[str, ...] | None], dict[str, Any]] = {}
        self.loaded = False

    def load(self) -> "FlowMap":
        """Load the semicolon-delimited mapping CSV."""
        rules: dict[tuple[str, tuple[str, ...] | None], dict[str, Any]] = {}
        with self.file.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames:
                reader.fieldnames = [field.lstrip("\ufeff") for field in reader.fieldnames]
            required = {
                "BAFU name",
                "BAFU category",
                "Ecoinvent name",
                "Ecoinvent category",
            }
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(
                    "Mapping CSV must contain BAFU name, BAFU category, "
                    "Ecoinvent name, and Ecoinvent category columns"
                )
            for pos, row in enumerate(reader, start=2):
                name = (row.get("BAFU name") or "").strip()
                if not name:
                    raise ValueError(f"Missing BAFU name in mapping row {pos}")
                cat = self.config.parsecat(row.get("BAFU category"))
                target_name = (row.get("Ecoinvent name") or "").strip()
                target_cat = self.config.parsecat(row.get("Ecoinvent category"))
                rules[(name, cat)] = {
                    "name": target_name or name,
                    "categories": target_cat or cat,
                    "raw_name": target_name,
                    "raw_categories": target_cat,
                }
        self.rules = rules
        self.loaded = True
        return self

    def target(
        self, name: str, categories: tuple[str, ...] | None
    ) -> dict[str, Any] | None:
        """Return the mapped target row for one BAFU flow."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Flow name must be a non-empty string")
        if not self.loaded:
            self.load()
        return self.rules.get((name.strip(), self.config.normcat(categories)))

    def _file(self, value: str | Path) -> Path:
        if not isinstance(value, (str, Path)):
            raise TypeError("Mapping CSV must be a string or Path")
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Mapping CSV not found: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Mapping CSV is not a file: {path}")
        return path


class Store:
    """Manage the Brightway project boundary for BAFU loading."""

    def __init__(self, project: str, log: logging.Logger | None = None) -> None:
        """Create a Brightway store object for one project."""
        if not isinstance(project, str) or not project.strip():
            raise ValueError("Project name must be a non-empty string")
        self.project = project.strip()
        self.log = log or logging.getLogger(__name__)
        self.bw2data: Any | None = None
        self.bw2io: Any | None = None

    def connect(self) -> "Store":
        """Import Brightway and select the configured project."""
        try:
            self.bw2data = importlib.import_module("bw2data")
            self.bw2io = importlib.import_module("bw2io")
        except ImportError as exc:
            raise ImportError("Install bw2data and bw2io before loading BAFU") from exc
        self.bw2data.projects.set_current(self.project)
        return self

    def exists(self, database: str) -> bool:
        """Return whether a Brightway database exists."""
        self._name(database)
        self._ready()
        return database in self.bw2data.databases

    def ensure(
        self,
        ecoinvent: str,
        biosphere: str,
        version: str,
        system: str,
        username: str | None = None,
        password: str | None = None,
        use_mp: bool = True,
    ) -> None:
        """Ensure the configured ecoinvent activity and biosphere databases exist."""
        self._name(ecoinvent)
        self._name(biosphere)
        self._ready()
        missing = [name for name in (ecoinvent, biosphere) if name not in self.bw2data.databases]
        if not missing:
            return
        importer = getattr(self.bw2io, "import_ecoinvent_release", None)
        if not callable(importer):
            raise RuntimeError("bw2io.import_ecoinvent_release is not available")
        status("WARN", "Missing Brightway database(s): " + ", ".join(missing))
        status("ACTION", "Importing the configured ecoinvent release")
        importer(
            version=self._text(version, "Ecoinvent version"),
            system_model=self._text(system, "Ecoinvent system model"),
            username=self._secret(username, "Ecoinvent username"),
            password=self._secret(password, "Ecoinvent password"),
            lci=True,
            lcia=True,
            biosphere_name=biosphere,
            biosphere_write_mode="patch",
            use_mp=use_mp,
        )
        still_missing = [
            name for name in (ecoinvent, biosphere) if name not in self.bw2data.databases
        ]
        if still_missing:
            raise RuntimeError(
                "Ecoinvent import finished but these databases are still missing: "
                + ", ".join(still_missing)
            )

    def flows(self, database: str) -> list[dict[str, Any]]:
        """Return elementary flow records from one Brightway database."""
        self._name(database)
        self._ready()
        if database not in self.bw2data.databases:
            raise ValueError(f"Brightway database does not exist: {database}")
        rows = []
        source = self.bw2data.Database(database)
        for node in progress(source, "Loading ecoinvent biosphere flows", len(source)):
            item = node.as_dict() if callable(getattr(node, "as_dict", None)) else node
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            code = item.get("code") or getattr(node, "code", None)
            if not name or not code:
                continue
            rows.append(
                {
                    "database": database,
                    "code": str(code),
                    "name": str(name),
                    "categories": tuple(item["categories"]) if item.get("categories") else None,
                    "unit": item.get("unit"),
                }
            )
        return rows

    def write(
        self,
        database: str,
        data: list[dict[str, Any]],
        biosphere: str,
        fallback: str = BAFU_BIOSPHERE,
        overwrite: bool = True,
    ) -> dict[str, int]:
        """Write mapped BAFU datasets into Brightway."""
        self._name(database)
        self._name(biosphere)
        self._name(fallback)
        if not isinstance(data, list) or not data:
            raise ValueError("Mapped BAFU data must be a non-empty list")
        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean")
        self._ready()
        if database in self.bw2data.databases and not overwrite:
            raise FileExistsError(f"Brightway database already exists: {database}")
        importer = self.bw2io.importers.base_lci.LCIImporter(db_name=database)
        importer.data = copy.deepcopy(data)
        status("ACTION", "Applying Brightway importer strategies")
        importer.apply_strategies()
        fallback_rows = self._fallback(importer.data, fallback)
        if fallback_rows:
            self._writefallback(fallback, fallback_rows)
        status("ACTION", "Matching internal BAFU technosphere exchanges")
        importer.match_database(fields=["name", "reference product", "location"])
        status("ACTION", f"Matching biosphere exchanges to {biosphere}")
        importer.match_database(
            biosphere,
            fields=["name", "categories"],
            edge_kinds=["biosphere"],
        )
        stat = importer.statistics(print_stats=False)
        if int(stat[2]):
            raise ValueError(
                "Brightway importer still has "
                f"{int(stat[2])} unlinked exchanges after mapping"
            )
        if database in self.bw2data.databases:
            status("WARN", f"Deleting existing Brightway database {database}")
            self.bw2data.Database(database).delete()
        status("ACTION", f"Writing Brightway database {database}")
        importer.write_database()
        return {
            "nodes": int(stat[0]),
            "edges": int(stat[1]),
            "unlinked": int(stat[2]),
            "multifunctional": int(stat[3]),
            "fallback_biosphere_flows": len(fallback_rows),
        }

    def _fallback(self, data: list[dict[str, Any]], database: str) -> list[dict[str, Any]]:
        rows: dict[tuple[str, tuple[str, ...] | None, str], dict[str, Any]] = {}
        for dataset in progress(data, "Preparing BAFU biosphere fallback flows", len(data)):
            for exchange in dataset.get("exchanges", []):
                if exchange.get("type") != "biosphere":
                    continue
                if exchange.get("_bafu_map_status") != "open":
                    continue
                name = str(exchange.get("name") or "").strip()
                categories = self._categories(exchange.get("categories"))
                unit = str(exchange.get("unit") or "unknown").strip() or "unknown"
                code = self._flowcode(name, categories, unit)
                rows.setdefault(
                    (name, categories, unit),
                    {
                        "code": code,
                        "name": name,
                        "categories": categories,
                        "unit": unit,
                        "type": "emission",
                    },
                )
                exchange["input"] = (database, code)
                exchange["_bafu_map_status"] = "bafu_biosphere"
        return sorted(rows.values(), key=lambda row: str(row["code"]))

    def _writefallback(self, database: str, rows: list[dict[str, Any]]) -> None:
        data = {}
        for row in rows:
            code = str(row["code"])
            data[(database, code)] = {
                "database": database,
                "code": code,
                "name": row["name"],
                "categories": row["categories"],
                "unit": row["unit"],
                "type": row["type"],
            }
        if database in self.bw2data.databases:
            self.bw2data.Database(database).delete()
        target = self.bw2data.Database(database)
        target.write(data)
        process = getattr(target, "process", None)
        if callable(process):
            process()
        status("OK", f"Wrote {len(rows)} unresolved flows to {database}")

    def _flowcode(self, name: str, categories: tuple[str, ...] | None, unit: str) -> str:
        payload = json.dumps(
            {"name": name, "categories": categories, "unit": unit},
            ensure_ascii=False,
            sort_keys=True,
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{BAFU_NAMESPACE}:{payload}"))

    def _categories(self, value: object) -> tuple[str, ...] | None:
        if not value:
            return None
        return tuple(str(item).strip().casefold() for item in value)

    def _ready(self) -> None:
        if self.bw2data is None or self.bw2io is None:
            self.connect()

    def _name(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Database name must be a non-empty string")

    def _text(self, value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    def _secret(self, value: str | None, name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string or None")
        return value.strip()


class BafuLoader:
    """Coordinate XML loading, flow mapping, and Brightway database writing."""

    def __init__(
        self,
        project: str,
        folder: str | Path = ".",
        xml: str | Path = "ecospold",
        csvfile: str | Path = "flows.csv",
        bafu: str = "bafu",
        ecoinvent: str = "ecoinvent-3.12-cutoff",
        biosphere: str = "ecoinvent-3.12-biosphere",
        version: str = "3.12",
        system: str = "cutoff",
        username: str | None = None,
        password: str | None = None,
        use_mp: bool = True,
        overwrite: bool = True,
        debug: bool = False,
    ) -> None:
        """Create a loader with validated paths and Brightway names."""
        self.folder = self._folder(folder)
        self.xml = self._path(xml, self.folder, "XML folder")
        self.csvfile = self._path(csvfile, self.folder, "Mapping CSV")
        self.project = self._text(project, "Project name")
        self.bafu = self._text(bafu, "BAFU database name")
        self.ecoinvent = self._text(ecoinvent, "Ecoinvent database name")
        self.biosphere = self._text(biosphere, "Biosphere database name")
        self.version = self._text(version, "Ecoinvent version")
        self.system = self._text(system, "Ecoinvent system model")
        self.username = self._secret(username, "Ecoinvent username")
        self.password = self._secret(password, "Ecoinvent password")
        if (self.username is None) != (self.password is None):
            raise ValueError(
                "Ecoinvent username and password must both be provided or both be None"
            )
        if not isinstance(use_mp, bool):
            raise TypeError("use_mp must be a boolean")
        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean")
        if not isinstance(debug, bool):
            raise TypeError("debug must be a boolean")
        self.use_mp = use_mp
        self.overwrite = overwrite
        self.debug = debug
        self.config = Config()
        self.log = self._logger()
        self.reader = Xml(self.xml, self.config)
        self.mapfile = FlowMap(self.csvfile, self.config)
        self.store = Store(self.project, self.log)
        self.data: list[dict[str, Any]] = []
        self.targets: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.stats: dict[str, int] = {}
        self.write_stats: dict[str, int] = {}

    def check(self) -> "BafuLoader":
        """Validate local files and Brightway project access."""
        if not self.xml.exists():
            raise FileNotFoundError(f"XML folder not found: {self.xml}")
        if not any(self.xml.glob("*.xml")):
            raise FileNotFoundError(f"No XML files found in {self.xml}")
        if not self.csvfile.exists():
            raise FileNotFoundError(f"Mapping CSV not found: {self.csvfile}")
        self.store.connect()
        status("OK", f"Ready to load XML from {self.xml}")
        status("OK", f"Ready to use mapping CSV {self.csvfile}")
        return self

    def load(self) -> "BafuLoader":
        """Load BAFU XML datasets and manual flow mapping rules."""
        self.data = self.reader.load(self.bafu)
        self.mapfile.load()
        self.stats = dict(self.reader.stat)
        status("OK", f"Loaded {len(self.data)} BAFU datasets")
        status("OK", f"Loaded {len(self.mapfile.rules)} flow mapping rows")
        return self

    def map(self) -> "BafuLoader":
        """Apply manual elementary-flow mappings against the ecoinvent biosphere."""
        if not self.data:
            raise RuntimeError("Run load() before map()")
        self.store.ensure(
            ecoinvent=self.ecoinvent,
            biosphere=self.biosphere,
            version=self.version,
            system=self.system,
            username=self.username,
            password=self.password,
            use_mp=self.use_mp,
        )
        self.targets = self.store.flows(self.biosphere)
        target_index = {
            (row["name"], self.config.normcat(row.get("categories"))): row
            for row in self.targets
        }
        unique = self._unique()
        rows = []
        data = copy.deepcopy(self.data)
        counts: Counter[str] = Counter()
        for item in unique:
            target = self.mapfile.target(item["bafu_name"], item["bafu_categories"])
            if target:
                key = (target["name"], self.config.normcat(target["categories"]))
                found = target_index.get(key)
                state = "manual_mapped" if found else "manual_target_missing"
            else:
                key = (item["bafu_name"], item["bafu_categories"])
                found = target_index.get(key)
                state = "exact_in_ecoinvent" if found else "needs_manual_mapping"
            counts[state] += 1
            rows.append(
                {
                    **item,
                    "mapping_status": state,
                    "ecoinvent_name": target["name"] if target else item["bafu_name"],
                    "ecoinvent_categories": target["categories"]
                    if target
                    else item["bafu_categories"],
                    "ecoinvent_code": found.get("code") if found else "",
                    "ecoinvent_unit": found.get("unit") if found else "",
                    "target_exists": bool(found),
                }
            )
        lookup = {(row["bafu_name"], row["bafu_categories"]): row for row in rows}
        for dataset in progress(data, "Applying flow mappings", len(data)):
            for exchange in dataset.get("exchanges", []):
                if exchange.get("type") != "biosphere":
                    continue
                key = (
                    str(exchange.get("name") or "").strip(),
                    self.config.normcat(exchange.get("categories")),
                )
                row = lookup.get(key)
                if not row:
                    exchange["_bafu_map_status"] = "open"
                    continue
                if row["mapping_status"] == "manual_mapped" and row["target_exists"]:
                    exchange["name"] = row["ecoinvent_name"]
                    exchange["categories"] = row["ecoinvent_categories"]
                    exchange["_bafu_map_status"] = "manual_mapped"
                    exchange["_bafu_target_code"] = row["ecoinvent_code"]
                elif row["mapping_status"] == "exact_in_ecoinvent":
                    exchange["_bafu_map_status"] = "exact_in_ecoinvent"
                    exchange["_bafu_target_code"] = row["ecoinvent_code"]
                else:
                    exchange["_bafu_map_status"] = "open"
        self.data = data
        self.rows = rows
        self.stats.update(
            {
                "unique_biosphere": len(rows),
                "manual_mapped": counts["manual_mapped"],
                "manual_target_missing": counts["manual_target_missing"],
                "exact_in_ecoinvent": counts["exact_in_ecoinvent"],
                "needs_manual_mapping": counts["needs_manual_mapping"],
                "resolved_unique": counts["manual_mapped"] + counts["exact_in_ecoinvent"],
                "unresolved_unique": counts["manual_target_missing"]
                + counts["needs_manual_mapping"],
            }
        )
        self._reports()
        status("SUMMARY", json.dumps(self.stats, sort_keys=True))
        return self

    def write(self) -> dict[str, int]:
        """Write the mapped BAFU database into the configured Brightway project."""
        if not self.data:
            raise RuntimeError("Run load() and map() before write()")
        self.write_stats = self.store.write(
            database=self.bafu,
            data=self.data,
            biosphere=self.biosphere,
            fallback=BAFU_BIOSPHERE,
            overwrite=self.overwrite,
        )
        status("OK", f"Wrote Brightway database {self.bafu}")
        return dict(self.write_stats)

    def run(self, write: bool = True) -> "BafuLoader":
        """Run check, load, map, and optionally write in order."""
        if not isinstance(write, bool):
            raise TypeError("write must be a boolean")
        self.check().load().map()
        if write:
            self.write()
        return self

    def _unique(self) -> list[dict[str, Any]]:
        found: dict[tuple[str, tuple[str, ...] | None, str | None], dict[str, Any]] = {}
        for dataset in progress(self.data, "Collecting unique BAFU flows", len(self.data)):
            for exchange in dataset.get("exchanges", []):
                if exchange.get("type") != "biosphere":
                    continue
                name = str(exchange.get("name") or "").strip()
                categories = self.config.normcat(exchange.get("categories"))
                unit = str(exchange.get("unit") or "").strip() or None
                key = (name, categories, unit)
                row = found.setdefault(
                    key,
                    {
                        "bafu_name": name,
                        "bafu_categories": categories,
                        "bafu_unit": unit,
                        "exchange_count": 0,
                        "dataset_count": 0,
                        "total_abs_amount": 0.0,
                        "_datasets": set(),
                        "example_datasets": [],
                    },
                )
                row["exchange_count"] += 1
                row["total_abs_amount"] += self._amount(exchange.get("amount"))
                dataset_name = str(dataset.get("name") or "").strip()
                if dataset_name and dataset_name not in row["_datasets"]:
                    row["_datasets"].add(dataset_name)
                    if len(row["example_datasets"]) < 5:
                        row["example_datasets"].append(dataset_name)
        rows = []
        for row in found.values():
            row["dataset_count"] = len(row["_datasets"])
            row.pop("_datasets", None)
            rows.append(row)
        return sorted(
            rows,
            key=lambda row: (
                row["bafu_name"],
                str(row["bafu_categories"]),
                str(row["bafu_unit"]),
            ),
        )

    def _reports(self) -> None:
        out = self.folder / "output"
        out.mkdir(parents=True, exist_ok=True)
        fields = [
            "bafu_name",
            "bafu_categories",
            "bafu_unit",
            "exchange_count",
            "dataset_count",
            "total_abs_amount",
            "mapping_status",
            "ecoinvent_name",
            "ecoinvent_categories",
            "ecoinvent_code",
            "ecoinvent_unit",
            "target_exists",
            "example_datasets",
        ]
        self._csv(out / "biosphere_mapping_audit.csv", self.rows, fields)
        open_rows = [
            row
            for row in self.rows
            if row["mapping_status"] in {"manual_target_missing", "needs_manual_mapping"}
        ]
        self._csv(out / "unmapped_flows_report.csv", open_rows, fields)
        self._csv(
            out / "summary.csv",
            [{"field": key, "value": value} for key, value in sorted(self.stats.items())],
            ["field", "value"],
        )

    def _csv(self, file: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
        with file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: self._clean(row.get(field)) for field in fields})
        status("FILE", f"Wrote {file}")

    def _logger(self) -> logging.Logger:
        logger = logging.getLogger("bafu")
        logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(handler)
        return logger

    def _folder(self, value: str | Path) -> Path:
        if not isinstance(value, (str, Path)):
            raise TypeError("Folder must be a string or Path")
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Folder not found: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a folder: {path}")
        return path

    def _path(self, value: str | Path, base: Path, name: str) -> Path:
        if not isinstance(value, (str, Path)):
            raise TypeError(f"{name} must be a string or Path")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"{name} not found: {path}")
        return path

    def _text(self, value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    def _secret(self, value: str | None, name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string or None")
        return value.strip()

    def _amount(self, value: object) -> float:
        try:
            out = abs(float(value))
        except (TypeError, ValueError):
            return 0.0
        return out if math.isfinite(out) else 0.0

    def _clean(self, value: object) -> object:
        if value is None:
            return ""
        if isinstance(value, (tuple, list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, bool):
            return str(value)
        return value
