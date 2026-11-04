"""Tabular data: CSV, TSV, JSON, XML, YAML and XLSX, converted row by row.

Every reader yields ``(columns, rows)`` and every writer consumes them, so most pairs
stream: CSV/TSV/XLSX(openpyxl read_only)/XML(iterparse) in, and CSV/TSV/XLSX
(write_only)/JSON/YAML/XML out. JSON and YAML inputs and legacy XLS/ODS sheets (via
pandas) are loaded whole because their parsers aren't incremental.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from engines.base import (
    ConversionError,
    ConversionOptions,
    CorruptInputError,
    Engine,
    Pair,
    ProgressFn,
    formats_of,
    pairs,
)

DATA_FORMATS = ("csv", "tsv", "json", "xml", "yaml")
WORKBOOKS = ("xlsx", "xls", "ods")
Columns = list[str]
Rows = Iterator[list[Any]]
Table = tuple[Columns, Rows]

_INT = re.compile(r"^-?(0|[1-9]\d{0,17})$")
_FLOAT = re.compile(r"^-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")
_XML_NAME_BAD = re.compile(r"[^A-Za-z0-9_.-]")


def _coerce(value: str) -> Any:
    """Turn numeric-looking text from CSV/XML into numbers; empty cells into None."""
    if value == "":
        return None
    if _INT.match(value):
        return int(value)
    if _FLOAT.match(value):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _open_text(path: Path):
    """Open text as UTF-8 (BOM tolerated), falling back to Latin-1 for legacy files."""
    with path.open("rb") as probe:
        sample = probe.read(64 * 1024)
    try:
        sample.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "latin-1"
    return path.open(newline="", encoding=encoding)


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


# ---------- readers ----------

def _read_delimited(path: Path, delimiter: str) -> Table:
    fh = _open_text(path)
    reader = csv.reader(fh, delimiter=delimiter)
    columns = next(reader, None)
    if columns is None:
        fh.close()
        return [], iter(())

    def rows() -> Rows:
        with fh:
            for row in reader:
                yield [_coerce(v) for v in row]

    return columns, rows()


def _records_table(records: Any) -> Table:
    """Accept a list of objects, a list of lists, or an object wrapping one list."""
    if isinstance(records, dict):
        lists = [v for v in records.values() if isinstance(v, list)]
        records = lists[0] if len(lists) == 1 else [records]
    if not isinstance(records, list):
        raise CorruptInputError("Expected a list of records.")
    if records and all(isinstance(r, list) for r in records):
        header = [str(c) for c in records[0]]
        return header, iter([[_cell(v) for v in r] for r in records[1:]])
    columns: dict[str, None] = {}
    for record in records:
        if isinstance(record, dict):
            columns.update(dict.fromkeys(map(str, record)))
    keys = list(columns) or ["value"]

    def rows() -> Rows:
        for record in records:
            if isinstance(record, dict):
                yield [_cell(record.get(k)) for k in keys]
            else:
                yield [_cell(record)]

    return keys, rows()


def _read_json(path: Path) -> Table:
    try:
        with _open_text(path) as fh:
            return _records_table(json.load(fh))
    except json.JSONDecodeError as exc:
        raise CorruptInputError("This JSON file isn't valid.") from exc


def _read_yaml(path: Path) -> Table:
    import yaml

    try:
        with _open_text(path) as fh:
            return _records_table(yaml.safe_load(fh))  # safe_load: no arbitrary objects
    except yaml.YAMLError as exc:
        raise CorruptInputError("This YAML file isn't valid.") from exc


def _xml_records(path: Path) -> Iterator[dict[str, str]]:
    """Each child of the root element is a record; its attributes and children are fields."""
    from lxml import etree

    context = etree.iterparse(str(path), events=("start", "end"), resolve_entities=False,
                              no_network=True, huge_tree=False, load_dtd=False)
    depth = 0
    try:
        for event, element in context:
            if event == "start":
                depth += 1
                continue
            depth -= 1
            if depth == 1:  # finished a record element
                record = {k: v for k, v in element.attrib.items()}
                for child in element:
                    record[etree.QName(child).localname] = (child.text or "").strip()
                if not len(element) and not record and element.text and element.text.strip():
                    record[etree.QName(element).localname] = element.text.strip()
                yield record
                element.clear()
                while element.getprevious() is not None:
                    del element.getparent()[0]
    except etree.XMLSyntaxError as exc:
        raise CorruptInputError("This XML file isn't well-formed.") from exc


def _read_xml(path: Path) -> Table:
    columns: dict[str, None] = {}
    for record in _xml_records(path):  # first pass: discover columns without keeping rows
        columns.update(dict.fromkeys(record))
    keys = list(columns)

    def rows() -> Rows:
        for record in _xml_records(path):
            yield [_coerce(record.get(k, "")) for k in keys]

    return keys, rows()


def _read_xlsx(path: Path) -> Table:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises zipfile/KeyError/InvalidFileException
        raise CorruptInputError("This workbook couldn't be opened.") from exc
    sheet = workbook.worksheets[0]
    values = sheet.iter_rows(values_only=True)
    header = next(values, None)
    if header is None:
        workbook.close()
        return [], iter(())
    columns = [str(c) if c is not None else f"column_{i + 1}" for i, c in enumerate(header)]

    def rows() -> Rows:
        try:
            for row in values:
                yield list(row)
        finally:
            workbook.close()

    return columns, rows()


def _read_legacy_workbook(path: Path) -> Table:
    import pandas as pd

    try:
        frame = pd.read_excel(path, sheet_name=0, engine="odf" if path.suffix == ".ods" else "xlrd")
    except Exception as exc:  # pandas surfaces parser-specific errors
        raise CorruptInputError("This spreadsheet couldn't be read.") from exc
    frame = frame.astype(object).where(frame.notna(), None)
    return [str(c) for c in frame.columns], (list(r) for r in frame.itertuples(index=False, name=None))


READERS: dict[str, Callable[[Path], Table]] = {
    "csv": lambda p: _read_delimited(p, ","),
    "tsv": lambda p: _read_delimited(p, "\t"),
    "json": _read_json,
    "yaml": _read_yaml,
    "xml": _read_xml,
    "xlsx": _read_xlsx,
    "xls": _read_legacy_workbook,
    "ods": _read_legacy_workbook,
}


# ---------- writers ----------

def _write_delimited(out: Path, columns: Columns, rows: Iterable[list[Any]], delimiter: str) -> None:
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])


# Rows may be ragged (short CSV lines); zip(strict=False) keeps the cells that exist.
def _write_json(out: Path, columns: Columns, rows: Iterable[list[Any]]) -> None:
    with out.open("w", encoding="utf-8") as fh:
        fh.write("[")
        for index, row in enumerate(rows):
            fh.write(",\n  " if index else "\n  ")
            json.dump(dict(zip(columns, row, strict=False)), fh, ensure_ascii=False, default=str)
        fh.write("\n]\n")


def _write_yaml(out: Path, columns: Columns, rows: Iterable[list[Any]]) -> None:
    import yaml

    with out.open("w", encoding="utf-8") as fh:
        wrote = False
        for row in rows:
            record = {k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                      for k, v in zip(columns, row, strict=False)}
            yaml.safe_dump([record], fh, allow_unicode=True, sort_keys=False)
            wrote = True
        if not wrote:
            fh.write("[]\n")


def _xml_tag(name: str) -> str:
    tag = _XML_NAME_BAD.sub("_", name) or "field"
    return tag if tag[0].isalpha() or tag[0] == "_" else f"_{tag}"


def _write_xml(out: Path, columns: Columns, rows: Iterable[list[Any]]) -> None:
    tags = [_xml_tag(c) for c in columns]
    with out.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<rows>\n')
        for row in rows:
            fields = "".join(
                f"<{t}>{escape(str(v))}</{t}>" if v is not None else f"<{t}/>" for t, v in zip(tags, row, strict=False)
            )
            fh.write(f"  <row>{fields}</row>\n")
        fh.write("</rows>\n")


def _write_xlsx(out: Path, columns: Columns, rows: Iterable[list[Any]]) -> None:
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Sheet1")
    sheet.append(columns)
    for row in rows:
        sheet.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in row])
    workbook.save(out)


WRITERS: dict[str, Callable[[Path, Columns, Iterable[list[Any]]], None]] = {
    "csv": lambda o, c, r: _write_delimited(o, c, r, ","),
    "tsv": lambda o, c, r: _write_delimited(o, c, r, "\t"),
    "json": _write_json,
    "yaml": _write_yaml,
    "xml": _write_xml,
    "xlsx": _write_xlsx,
}


class DataEngine(Engine):
    """Tabular conversions where at least one side is a data format (CSV/TSV/JSON/XML/YAML).

    Workbook ↔ workbook and → PDF go through LibreOffice to keep formatting.
    """

    name = "data"

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs((*DATA_FORMATS, *WORKBOOKS), DATA_FORMATS) | pairs(DATA_FORMATS, ("xlsx",))

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        src, dst = formats_of(input_path, output_path)
        columns, rows = READERS[src](input_path)
        total = max(input_path.stat().st_size, 1)

        def tracked(source: Rows) -> Iterator[list[Any]]:
            # Approximate progress from rows emitted vs. a bytes-per-row estimate.
            for index, row in enumerate(source, 1):
                if progress and index % 5000 == 0:
                    progress(min(0.99, index * 64 / total))
                yield row

        try:
            WRITERS[dst](output_path, columns, tracked(rows))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise CorruptInputError("This file couldn't be parsed as a table.") from exc
        except OSError as exc:
            raise ConversionError("Couldn't write the converted table.") from exc
        return [output_path]
