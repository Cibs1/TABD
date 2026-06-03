from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        raise ValueError(f"Invalid cell reference: {cell_ref}")

    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value


class XlsxReader:
    """Small read-only XLSX reader for simple worksheet data.

    The CNE workbooks are single-sheet files and do not require formulas,
    styles, merged-cell reconstruction, or date handling. This keeps the ETL
    reproducible without requiring openpyxl just to parse the source files.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def iter_rows(self, sheet_index: int = 0):
        with ZipFile(self.path) as archive:
            shared_strings = self._shared_strings(archive)
            worksheet_path = self._worksheet_path(archive, sheet_index)
            root = ET.fromstring(archive.read(worksheet_path))

            for row in root.findall("a:sheetData/a:row", NS):
                values = {}
                for cell in row.findall("a:c", NS):
                    ref = cell.attrib.get("r", "A1")
                    values[column_index(ref)] = self._cell_value(cell, shared_strings)
                if values:
                    yield int(row.attrib.get("r", "0")), values

    def _shared_strings(self, archive: ZipFile) -> list[str]:
        try:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []

        strings = []
        for item in root.findall("a:si", NS):
            strings.append("".join((text.text or "") for text in item.iter(f"{{{NS['a']}}}t")))
        return strings

    def _worksheet_path(self, archive: ZipFile, sheet_index: int) -> str:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        sheets = workbook.find("a:sheets", NS)
        if sheets is None or sheet_index >= len(sheets):
            raise ValueError(f"Workbook {self.path} does not contain sheet index {sheet_index}")

        sheet = sheets[sheet_index]
        relation_id = sheet.attrib[f"{{{NS['r']}}}id"]
        target = rel_targets[relation_id]
        if not target.startswith("xl/"):
            target = "xl/" + target
        return target

    def _cell_value(self, cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.attrib.get("t")

        if cell_type == "inlineStr":
            inline = cell.find("a:is", NS)
            if inline is None:
                return ""
            return "".join((text.text or "") for text in inline.iter(f"{{{NS['a']}}}t")).strip()

        value = cell.find("a:v", NS)
        if value is None:
            return ""

        raw = value.text or ""
        if cell_type == "s":
            return shared_strings[int(raw)].strip()
        return raw.strip()
