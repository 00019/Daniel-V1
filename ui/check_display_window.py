import os
from datetime import date, datetime
from typing import Any, Optional

from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QInputDialog, QProgressDialog,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QLabel, QHeaderView, QMessageBox, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

from database.table import Table
from .manual_add_window import ManualAddWindow
from .check_io import CheckIOMixin
from .check_status import CheckStatusMixin
from .check_delete import CheckDeleteMixin
from .check_ocr import CheckOCRMixin
from .check_query import CheckQueryMixin


class CheckDisplayWindow(CheckIOMixin, CheckStatusMixin, CheckDeleteMixin, CheckOCRMixin, CheckQueryMixin, QWidget):
    back_to_home = Signal()

    COLUMNS = [
        "ID",
        "Check #",
        "Cleared",
        "Payee",
        "Drawer",
        "Drawee",
        "Amount",
        "Date",
        "Account",
        "Routing #",
        "Memo",
    ]

    FIELD_TO_COL = {
        "id": 0,
        "check_number": 1,
        "cleared": 2,
        "payee": 3,
        "drawer": 4,
        "drawee": 5,
        "amount": 6,
        "date": 7,
        "account": 8,
        "routing": 9,
        "memo": 10,
    }

    def __init__(self, table: Table, db_path: str):
        super().__init__()
        self.table = table
        self.db_path = db_path
        self.current_sort = "most_recent"
        self.shown_condition = "all_checks"
        self.query_active = False
        self.query_rows = None
        self.setup_ui()
        self.load_checks()

    def setup_ui(self):
        self.setWindowTitle(f"Check Database - {os.path.basename(self.db_path)}")
        self.resize(1450, 600)

        layout = QVBoxLayout()

        header_layout = QHBoxLayout()
        self.back_btn = QPushButton("← Back to Home")
        self.back_btn.clicked.connect(self.back_to_home.emit)
        header_layout.addWidget(self.back_btn)
        self.db_label = QLabel("")
        header_layout.addWidget(self.db_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        action_layout = QHBoxLayout()

        self.display_btn = QPushButton("Display")
        display_menu = QMenu(self)
        sort_menu = QMenu("Sort By", self)
        sort_menu.addAction("Most Recent", lambda: self.set_sort("most_recent"))
        sort_menu.addAction("Oldest", lambda: self.set_sort("oldest"))
        sort_menu.addAction("Largest Payment", lambda: self.set_sort("largest"))
        sort_menu.addAction("Smallest Payment", lambda: self.set_sort("smallest"))
        display_menu.addMenu(sort_menu)
        show_menu = QMenu("Show", self)
        show_menu.addAction("All Checks", lambda: self.set_show("all_checks"))
        show_menu.addAction("Cleared Checks", lambda: self.set_show("cleared_checks"))
        show_menu.addAction("Uncleared Checks", lambda: self.set_show("uncleared_checks"))
        display_menu.addMenu(show_menu)
        display_menu.addSeparator()
        display_menu.addAction("Clear Query Results", self.clear_query)
        self.display_btn.setMenu(display_menu)
        action_layout.addWidget(self.display_btn)

        self.addition_btn = QPushButton("Add Check(s)")
        addition_menu = QMenu(self)
        addition_menu.addAction("Add Manually", self.manual_addition)
        addition_menu.addAction("Scan Check", self.automatic_addition)
        import_submenu = QMenu("Import Check", self)
        import_submenu.addAction("From CSV", self._import_from_csv)
        import_submenu.addAction("From Excel (.xlsx)", self._import_from_excel)
        import_submenu.addAction("From QIF", self._import_from_qif)
        import_submenu.addAction("From SQL Database (.db)", self._import_from_db)
        addition_menu.addMenu(import_submenu)
        self.addition_btn.setMenu(addition_menu)
        action_layout.addWidget(self.addition_btn)

        self.delete_btn = QPushButton("Delete")
        delete_menu = QMenu(self)
        delete_menu.addAction("Delete Selected", self.delete_selected_checks)
        delete_menu.addAction("Delete Shown", self.delete_shown_checks)
        self.delete_btn.setMenu(delete_menu)
        action_layout.addWidget(self.delete_btn)

        self.status_btn = QPushButton("Status")
        status_menu = QMenu(self)
        selected_menu = QMenu("Selected", self)
        selected_menu.addAction("Clear (set cleared=Yes)", self.clear_selected_checks)
        selected_menu.addAction("Unclear (set cleared=No)", self.unclear_selected_checks)
        selected_menu.addAction("Toggle (Yes↔No)", self.toggle_selected_checks)
        status_menu.addMenu(selected_menu)
        shown_menu = QMenu("Shown (current filter)", self)
        shown_menu.addAction("Clear (set cleared=Yes)", self.clear_shown_checks)
        shown_menu.addAction("Unclear (set cleared=No)", self.unclear_shown_checks)
        shown_menu.addAction("Toggle (Yes↔No)", self.toggle_shown_checks)
        status_menu.addMenu(shown_menu)
        self.status_btn.setMenu(status_menu)
        action_layout.addWidget(self.status_btn)

        self.query_btn = QPushButton("Query")
        self.query_menu = QMenu(self)
        self.query_menu.addAction("Manual Query", self.manual_query)
        self.query_menu.addAction("Assisted Query", self.assisted_query)
        self.query_btn.setMenu(self.query_menu)
        action_layout.addWidget(self.query_btn)

        self.export_btn = QPushButton("Export")
        export_menu = QMenu(self)
        export_all_menu = QMenu("Export All", self)
        export_all_menu.addAction("CSV", lambda: self._export_all_to("csv"))
        export_all_menu.addAction("Excel (.xlsx)", lambda: self._export_all_to("excel"))
        export_all_menu.addAction("QIF (Quicken)", lambda: self._export_all_to("qif"))
        export_all_menu.addAction("SQL Database (.db)", lambda: self._export_all_to("db"))
        export_all_menu.addAction("Append to Existing Database", self._append_all_to_db)
        export_menu.addMenu(export_all_menu)
        export_displayed_menu = QMenu("Export Displayed", self)
        export_displayed_menu.addAction("CSV", lambda: self._export_displayed_to("csv"))
        export_displayed_menu.addAction("Excel (.xlsx)", lambda: self._export_displayed_to("excel"))
        export_displayed_menu.addAction("QIF (Quicken)", lambda: self._export_displayed_to("qif"))
        export_displayed_menu.addAction("SQL Database (.db)", lambda: self._export_displayed_to("db"))
        export_displayed_menu.addAction("Append to Existing Database", self._append_displayed_to_db)
        export_menu.addMenu(export_displayed_menu)
        export_selected_menu = QMenu("Export Selected", self)
        export_selected_menu.addAction("CSV", lambda: self._export_selected_to("csv"))
        export_selected_menu.addAction("Excel (.xlsx)", lambda: self._export_selected_to("excel"))
        export_selected_menu.addAction("QIF (Quicken)", lambda: self._export_selected_to("qif"))
        export_selected_menu.addAction("SQL Database (.db)", lambda: self._export_selected_to("db"))
        export_selected_menu.addAction("Append to Existing Database", self._append_selected_to_db)
        export_menu.addMenu(export_selected_menu)
        self.export_btn.setMenu(export_menu)
        action_layout.addWidget(self.export_btn)

        layout.addLayout(action_layout)

        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setWordWrap(False)
        self.table_view.setTextElideMode(Qt.ElideRight)
        self.table_view.verticalHeader().setDefaultSectionSize(28)
        self.table_view.doubleClicked.connect(self.on_row_double_clicked)
        layout.addWidget(self.table_view)

        self.setLayout(layout)
        self._update_display_button_text()

    def set_sort(self, sort_option: str):
        self.current_sort = sort_option
        self.query_active = False
        self.query_rows = None
        self._update_display_button_text()
        self.load_checks()

    def set_show(self, show_option: str):
        self.shown_condition = show_option
        self.query_active = False
        self.query_rows = None
        self._update_display_button_text()
        self.load_checks()

    def _update_display_button_text(self):
        if self.query_active:
            self.display_btn.setText("Display (Query Results)")
            return
        sort_names = {
            "most_recent": "Most Recent",
            "oldest": "Oldest",
            "largest": "Largest",
            "smallest": "Smallest",
        }
        show_names = {
            "all_checks": "All",
            "cleared_checks": "Cleared",
            "uncleared_checks": "Uncleared",
        }
        self.display_btn.setText(
            f"Display: {show_names[self.shown_condition]} | {sort_names[self.current_sort]}"
        )

    def refresh_all(self):
        self.load_checks()

    def _to_int(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False

    def _to_str(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _to_float(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0
        try:
            return float(value)
        except Exception:
            return 0.0

    def _to_date(self, value: Any):
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            text = value.strip()
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    pass
        return None

    def _format_date_text(self, value: Any) -> str:
        parsed = self._to_date(value)
        return parsed.strftime("%Y-%m-%d") if parsed else ""

    def _make_text_item(self, text: str, tooltip: Optional[str] = None) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        if tooltip:
            item.setToolTip(tooltip)
        return item

    def _make_checkbox_item(self, checked: bool) -> QStandardItem:
        item = QStandardItem("")
        item.setEditable(False)
        item.setCheckable(True)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def load_checks(self):
        self.table.load_from_db()

        if self.query_active and self.query_rows is not None:
            self._render_rows(self.query_rows)
            self.db_label.setText(
                f"Database: {os.path.basename(self.db_path)} - {len(self.query_rows)} matches"
            )
            return

        if self.current_sort == "most_recent":
            self.table.order_by("date", ascending=False)
        elif self.current_sort == "oldest":
            self.table.order_by("date", ascending=True)
        elif self.current_sort == "largest":
            self.table.order_by("amount", ascending=False)
        elif self.current_sort == "smallest":
            self.table.order_by("amount", ascending=True)

        checks = list(Table.checks)

        if self.shown_condition == "cleared_checks":
            checks = [c for c in checks if self._to_bool(c.get("cleared"))]
        elif self.shown_condition == "uncleared_checks":
            checks = [c for c in checks if not self._to_bool(c.get("cleared"))]

        rows = []
        for c in checks:
            rows.append((
                self._to_int(c.get("id")),
                self._to_int(c.get("check_number")),
                self._to_bool(c.get("cleared")),
                self._to_str(c.get("payee")),
                self._to_str(c.get("drawer")),
                self._to_str(c.get("drawee")),
                self._to_float(c.get("amount")),
                self._to_date(c.get("date")),
                self._to_str(c.get("account")),
                self._to_str(c.get("routing")),
                self._to_str(c.get("memo")),
            ))

        self._render_rows(rows)
        self.db_label.setText(
            f"Database: {os.path.basename(self.db_path)} - {len(checks)} checks"
        )

    def _render_rows(self, rows):
        model = QStandardItemModel()
        model.setColumnCount(len(self.COLUMNS))

        for i, title in enumerate(self.COLUMNS):
            model.setHeaderData(i, Qt.Horizontal, title, Qt.DisplayRole)
            model.setHeaderData(i, Qt.Horizontal, int(Qt.AlignCenter), Qt.TextAlignmentRole)

        for row_data in rows:
            row_items = [
                self._make_text_item("" if row_data[0] is None else str(row_data[0])),
                self._make_text_item("" if row_data[1] is None else str(row_data[1])),
                self._make_checkbox_item(bool(row_data[2])),
                self._make_text_item(row_data[3] or ""),
                self._make_text_item(row_data[4] or ""),
                self._make_text_item(row_data[5] or ""),
                self._make_text_item(f"${row_data[6]:.2f}"),
                self._make_text_item(self._format_date_text(row_data[7])),
                self._make_text_item(row_data[8] or ""),
                self._make_text_item(row_data[9] or ""),
                self._make_text_item(row_data[10] or "", tooltip=row_data[10] or ""),
            ]
            model.appendRow(row_items)

        self.table_view.setModel(model)

        header = self.table_view.horizontalHeader()
        header.setVisible(True)
        header.setEnabled(True)
        header.setHighlightSections(True)

        self.table_view.setColumnHidden(self.FIELD_TO_COL["id"], True)
        self.table_view.setColumnHidden(self.FIELD_TO_COL["memo"], False)

        column_widths = {
            "check_number": 80,
            "cleared": 70,
            "payee": 150,
            "drawer": 150,
            "drawee": 150,
            "amount": 100,
            "date": 100,
            "account": 120,
            "routing": 140,
            "memo": 400,
        }

        for field_name, width in column_widths.items():
            col = self.FIELD_TO_COL[field_name]
            self.table_view.setColumnWidth(col, width)

        for col_idx in range(len(self.COLUMNS)):
            header.setSectionResizeMode(col_idx, QHeaderView.Interactive)

        self.table_view.verticalHeader().setDefaultSectionSize(28)
        self.table_view.repaint()
        header.repaint()

    def update_table(self, table: Table, db_path: str):
        self.table = table
        self.db_path = db_path
        self.setWindowTitle(f"Check Database - {os.path.basename(db_path)}")
        self.query_active = False
        self.query_rows = None
        self._update_display_button_text()
        self.load_checks()

    def add_check(self):
        QMessageBox.information(
            self,
            "Add Check",
            "Add check functionality to be implemented (ported next)."
        )

    def edit_check(self):
        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            return
        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a check to edit.")
            return
        row = selected_rows[0].row()
        model = self.table_view.model()
        if model is None:
            return

        def cell(col_name):
            return model.index(row, self.FIELD_TO_COL[col_name]).data() or ""

        check_id_raw = cell("id")
        try:
            check_id = int(check_id_raw)
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Error", "Could not read ID for selected row.")
            return

        raw_amount = cell("amount").replace("$", "").strip()

        data = {
            "check_number": cell("check_number"),
            "payee":        cell("payee"),
            "drawer":       cell("drawer"),
            "drawee":       cell("drawee"),
            "amount":       raw_amount,
            "date":         cell("date"),
            "account":      cell("account"),
            "routing":      cell("routing"),
            "memo":         cell("memo"),
            "cleared": model.item(row, self.FIELD_TO_COL["cleared"]).checkState() == Qt.Checked,
        }
        data["id"] = check_id

        self.edit_window = ManualAddWindow(self, self.table, data=data)
        self.edit_window.check_saved.connect(self.refresh_all)
        self.edit_window.show()

    def on_row_double_clicked(self, index):
        self.edit_check()

    def manual_addition(self):
        self.manual_add_window = ManualAddWindow(self, self.table)
        self.manual_add_window.check_saved.connect(self.refresh_all)
        self.manual_add_window.show()
