"""Extract normalized regression data from the reference spreadsheet."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DEFAULT_OUTPUT_PATH = Path("tests/data/spreadsheet_reference.json")
MAIN_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _load_cells(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", MAIN_NS):
                shared_strings.append(
                    "".join(text.text or "" for text in item.findall(".//a:t", MAIN_NS))
                )

        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        cells: dict[str, str] = {}
        for row in sheet.findall(".//a:sheetData/a:row", MAIN_NS):
            for cell in row.findall("a:c", MAIN_NS):
                ref = cell.attrib["r"]
                value = cell.find("a:v", MAIN_NS)
                if value is None:
                    continue
                text = value.text or ""
                if cell.attrib.get("t") == "s":
                    text = shared_strings[int(text)]
                cells[ref] = text
        return cells


def extract_reference(path: Path) -> dict[str, object]:
    """Extract the normalized regression payload from the workbook."""
    cells = _load_cells(path)
    labels = [cells[f"{column}4"] for column in ["D", "E", "F", "G", "H", "I"]]
    expected_margin_columns = dict(zip(["D", "E", "F", "G", "H", "I"], labels, strict=True))
    opposed_win_columns = dict(zip(["M", "N", "O", "P", "Q", "R"], labels, strict=True))
    static_gt_columns = dict(zip(["M", "N", "O", "P", "Q", "R"], labels, strict=True))
    static_eq_columns = dict(zip(["V", "W", "X", "Y", "Z", "AA"], labels, strict=True))

    reference: dict[str, object] = {
        "labels": labels,
        "opposed_expected_margin": {attacker: {} for attacker in labels},
        "opposed_win": {attacker: {} for attacker in labels},
        "static_gt": {attacker: {} for attacker in labels},
        "static_eq": {attacker: {} for attacker in labels},
    }

    for row in range(5, 11):
        defender = cells[f"C{row}"]
        for column, attacker in expected_margin_columns.items():
            reference["opposed_expected_margin"][attacker][defender] = float(
                cells[f"{column}{row}"]
            )
        for column, attacker in opposed_win_columns.items():
            reference["opposed_win"][attacker][defender] = float(cells[f"{column}{row}"])

    for row in range(13, 37):
        dc = str(int(float(cells[f"C{row}"])))
        for column, attacker in static_gt_columns.items():
            ref = f"{column}{row}"
            if cells.get(ref):
                reference["static_gt"][attacker][dc] = float(cells[ref])
        for column, attacker in static_eq_columns.items():
            ref = f"{column}{row}"
            if cells.get(ref):
                reference["static_eq"][attacker][dc] = float(cells[ref])

    return reference


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract normalized regression data from the validation spreadsheet.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the roll-probability spreadsheet (.xlsx).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "Optional JSON output path. Defaults to "
            f"'{DEFAULT_OUTPUT_PATH.as_posix()}'. Use '-' to print to stdout."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the spreadsheet extraction CLI."""
    args = _build_parser().parse_args(argv)
    workbook_path = args.input.expanduser().resolve()
    if not workbook_path.is_file():
        raise SystemExit(f"Input workbook not found: {workbook_path}")

    reference = extract_reference(workbook_path)
    payload = json.dumps(reference, indent=2, sort_keys=True)

    if str(args.output) == "-":
        print(payload)
        return 0

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload + "\n", encoding="utf-8")
    print(f"Wrote normalized reference data to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
