from __future__ import annotations

import csv
import json

import pytest
import yaml
from openpyxl import load_workbook

from engines.base import CorruptInputError
from engines.data import DataEngine
from tests.conftest import convert, detected, requires

ENGINE = DataEngine()


@pytest.mark.parametrize("dst", ["json", "yaml", "xml", "tsv", "xlsx"])
def test_csv_to_each(samples, tmp_path, dst: str) -> None:
    [out] = convert(ENGINE, samples.get("csv"), dst, tmp_path)
    assert detected(out) == dst


def test_csv_to_json_types_and_quoting(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("csv"), "json", tmp_path)
    rows = json.loads(out.read_text())
    assert rows[0] == {"name": "Ada", "age": 36, "city": "London"}
    assert rows[2] == {"name": "Smith, J", "age": None, "city": "Paris"}


@pytest.mark.parametrize("src", ["json", "yaml", "xml", "xlsx", "tsv"])
def test_each_to_csv(samples, tmp_path, src: str) -> None:
    [out] = convert(ENGINE, samples.get(src), "csv", tmp_path)
    rows = list(csv.reader(out.open()))
    assert rows[0][:2] == ["name", "age"] and rows[1][:2] == ["Ada", "36"]


def test_xlsx_round_trip(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("json"), "xlsx", tmp_path)
    sheet = load_workbook(out, read_only=True).active
    assert list(sheet.iter_rows(values_only=True)) == [("name", "age"), ("Ada", 36), ("Linus", 28)]


def test_yaml_output_is_safe_loadable(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("csv"), "yaml", tmp_path)
    assert yaml.safe_load(out.read_text())[1]["city"] == "Helsinki"


@requires("soffice")
@pytest.mark.parametrize("src", ["xls", "ods"])
def test_legacy_workbooks_to_json(samples, tmp_path, src: str) -> None:
    [out] = convert(ENGINE, samples.get(src), "json", tmp_path)
    assert json.loads(out.read_text())[0]["name"] == "Ada"


def test_xml_entities_are_not_expanded(tmp_path) -> None:
    evil = tmp_path / "evil.xml"
    evil.write_text('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                    "<r><row><a>&x;</a></row></r>")
    [out] = convert(ENGINE, evil, "json", tmp_path)
    assert "root:" not in out.read_text()


@pytest.mark.parametrize(("name", "content"), [("bad.json", "{not json"), ("bad.yaml", "a: [unclosed"),
                                               ("bad.xml", "<a><b></a>")])
def test_corrupted_inputs(tmp_path, name: str, content: str) -> None:
    src = tmp_path / name
    src.write_text(content)
    with pytest.raises(CorruptInputError):
        convert(ENGINE, src, "csv", tmp_path)
