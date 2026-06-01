from __future__ import annotations

import csv
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialogButtonBox, QComboBox, QGroupBox,
)
from PySide6.QtCore import Qt




_CANONICAL = ["check_number", "cleared", "payee", "drawer", "drawee",
               "amount", "date", "account", "routing", "memo"]


_ALIASES: Dict[str, List[str]] = {
    "check_number": ["check_number", "check number", "check#", "check_no",
                     "checkno", "no", "number", "chk#", "chkno"],
    "cleared":      ["cleared", "clear", "paid", "is_cleared"],
    "payee":        ["payee", "pay to", "pay_to", "payer", "drawn by"],
    "drawer":       ["drawer", "drawn by", "writer", "maker", "issuer"],
    "drawee":       ["drawee", "bank", "bank name", "paying bank"],
    "amount":       ["amount", "value", "sum", "total", "amt", "dollar", "$"],
    "date":         ["date", "date_issued", "issued", "date issued", "check date"],
    "memo":         ["memo", "note", "notes", "description", "desc", "subject"],
    "account":      ["account", "acct", "account_number", "account number",
                     "bank account", "acct#"],
    "routing":      ["routing", "routing number", "route", "rt", "transit", "transit number"],
}


def _auto_map(headers: List[str]) -> Dict[str, Optional[int]]:
    mapping: Dict[str, Optional[int]] = {f: None for f in _CANONICAL}
    used: set = set()
    for field, aliases in _ALIASES.items():
        for idx, h in enumerate(headers):
            if idx in used:
                continue
            if h.strip().lower() in aliases:
                mapping[field] = idx
                used.add(idx)
                break
    return mapping


def _parse_date(text: str):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
                "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _parse_bool(text: str) -> bool:
    return text.strip().lower() in {"1", "true", "yes", "y", "cleared", "paid"}




class ImportDialog(QDialog):

    _PREVIEW_ROWS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Checks from CSV")
        self.setMinimumSize(720, 540)

        self._raw_rows: List[List[str]] = []
        self._csv_headers: List[str]   = []
        self._combos: Dict[str, QComboBox] = {}

        self._build_ui()



    def _build_ui(self):
        layout = QVBoxLayout(self)


        file_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a CSV file…")
        self._path_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(QLabel("CSV file:"))
        file_row.addWidget(self._path_edit, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)


        map_box = QGroupBox(
            "Column mapping  "
            "(required: check_number · payee · amount · date)"
        )
        map_form = QFormLayout()
        for field in _CANONICAL:
            cb = QComboBox()
            cb.addItem("— skip —")
            self._combos[field] = cb
            lbl = QLabel(field)
            lbl.setMinimumWidth(130)
            map_form.addRow(lbl, cb)
        map_box.setLayout(map_form)
        layout.addWidget(map_box)


        layout.addWidget(QLabel(f"Preview (first {self._PREVIEW_ROWS} rows):"))
        self._preview = QTableWidget()
        self._preview.setMaximumHeight(150)
        self._preview.setEditTriggers(QTableWidget.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        layout.addWidget(self._preview)

        self._status_lbl = QLabel("")
        layout.addWidget(self._status_lbl)


        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok_btn = btn_box.button(QDialogButtonBox.Ok)
        self._ok_btn.setText("Import")
        self._ok_btn.setEnabled(False)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)



    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV",
            "",
            "CSV Files (*.csv);;Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        self._path_edit.setText(path)
        self._load_csv(path)

    def _load_csv(self, path: str):
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                all_rows = list(csv.reader(fh))
        except Exception as exc:
            QMessageBox.critical(self, "Read Error", f"Could not read file:\n{exc}")
            return

        if not all_rows:
            self._status_lbl.setText("⚠  File is empty.")
            return

        self._csv_headers = all_rows[0]
        self._raw_rows    = all_rows[1:]

        if not self._raw_rows:
            self._status_lbl.setText("⚠  File contains only a header row — no data.")
            return


        auto = _auto_map(self._csv_headers)
        for field, cb in self._combos.items():
            cb.clear()
            cb.addItem("— skip —")
            for i, h in enumerate(self._csv_headers):
                cb.addItem(f"[{i}] {h}", userData=i)
            detected = auto.get(field)

            cb.setCurrentIndex(detected + 1 if detected is not None else 0)


        ncols = len(self._csv_headers)
        nrows = min(self._PREVIEW_ROWS, len(self._raw_rows))
        self._preview.setColumnCount(ncols)
        self._preview.setRowCount(nrows)
        self._preview.setHorizontalHeaderLabels(self._csv_headers)
        for r, row in enumerate(self._raw_rows[:nrows]):
            for c in range(ncols):
                val = row[c] if c < len(row) else ""
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self._preview.setItem(r, c, item)
        self._preview.resizeColumnsToContents()

        total = len(self._raw_rows)
        self._status_lbl.setText(
            f"✓  {total} data row{'s' if total != 1 else ''} detected."
        )
        self._ok_btn.setEnabled(True)



    def _on_accept(self):
        required = ["check_number", "payee", "amount", "date"]
        missing = [f for f in required if self._combos[f].currentIndex() == 0]
        if missing:
            QMessageBox.warning(
                self, "Required Columns Missing",
                f"Please map these required columns:\n  {', '.join(missing)}"
            )
            return
        self.accept()

    def _col_idx(self, field: str) -> Optional[int]:
        cb = self._combos[field]
        if cb.currentIndex() == 0:
            return None
        return cb.currentData()



    def get_records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        errors:  List[str]            = []

        for row_num, row in enumerate(self._raw_rows, start=2):

            def cell(field: str) -> str:
                idx = self._col_idx(field)
                if idx is None or idx >= len(row):
                    return ""
                return row[idx].strip()

            try:
                cn_s = cell("check_number")
                if not cn_s:
                    raise ValueError("check_number is empty")
                check_number = int(cn_s)

                amt_s = cell("amount").replace("$", "").replace(",", "")
                if not amt_s:
                    raise ValueError("amount is empty")
                amount = float(amt_s)

                date_s  = cell("date")
                date_obj = _parse_date(date_s) if date_s else None
                if date_obj is None:
                    raise ValueError(
                        f"cannot parse date '{date_s}' "
                        "(expected YYYY-MM-DD, MM/DD/YYYY, or DD/MM/YYYY)"
                    )

                payee = cell("payee")
                if not payee:
                    raise ValueError("payee is empty")

                records.append({
                    "check_number": check_number,
                    "cleared":      _parse_bool(cell("cleared")),
                    "payee":        payee,
                    "drawer":       cell("drawer"),
                    "drawee":       cell("drawee"),
                    "amount":       amount,
                    "date":         date_obj,
                    "account":      cell("account"),
                    "routing":      cell("routing"),
                    "memo":         cell("memo"),
                })

            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")

        if errors:
            preview = "\n".join(errors[:10])
            extra   = f"\n…and {len(errors) - 10} more." if len(errors) > 10 else ""
            QMessageBox.warning(
                self, "Import Warnings",
                f"Skipped {len(errors)} row(s) due to errors:\n\n{preview}{extra}"
            )

        return records
