from datetime import date as pydate
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QDateEdit, QDoubleSpinBox, QSpinBox,
    QCheckBox, QComboBox, QPushButton, QLabel,
    QGroupBox, QDialogButtonBox
)
from PySide6.QtCore import QDate


class QueryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Query Checks")
        self.setMinimumWidth(520)
        self._build_ui()

    def _toggle_exact_mode(self, checked: bool):
        self.amount_min.setEnabled(not checked)
        self.amount_max.setEnabled(not checked)
        self.use_amount_max.setEnabled(not checked)
        if checked:
            self.use_amount_max.setChecked(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        search_box = QGroupBox("Text search")
        sf = QFormLayout()
        self.global_input = QLineEdit()
        self.global_input.setPlaceholderText("Searches payee, drawer, drawee, routing, memo, account…")
        sf.addRow("Anywhere:", self.global_input)
        self.payee_input = QLineEdit()
        sf.addRow("Payee contains:", self.payee_input)
        self.drawer_input = QLineEdit()
        sf.addRow("Drawer contains:", self.drawer_input)
        self.drawee_input = QLineEdit()
        sf.addRow("Drawee contains:", self.drawee_input)
        self.routing_input = QLineEdit()
        sf.addRow("Routing exact:", self.routing_input)
        self.memo_input = QLineEdit()
        sf.addRow("Memo contains:", self.memo_input)
        self.account_input = QLineEdit()
        sf.addRow("Account exact:", self.account_input)
        search_box.setLayout(sf)
        layout.addWidget(search_box)

        num_box = QGroupBox("Amount / check number")
        nf = QFormLayout()
        amt_row = QHBoxLayout()
        self.amount_min = QDoubleSpinBox()
        self.amount_min.setRange(0, 9_999_999)
        self.amount_min.setDecimals(2)
        self.amount_min.setPrefix("$")
        self.amount_max = QDoubleSpinBox()
        self.amount_max.setRange(0, 9_999_999)
        self.amount_max.setDecimals(2)
        self.amount_max.setPrefix("$")
        self.use_amount_max = QCheckBox("Use max")
        self.use_amount_max.toggled.connect(self.amount_max.setEnabled)
        self.amount_max.setEnabled(False)
        amt_row.addWidget(QLabel("Min"))
        amt_row.addWidget(self.amount_min)
        amt_row.addWidget(QLabel("Max"))
        amt_row.addWidget(self.amount_max)
        amt_row.addWidget(self.use_amount_max)
        nf.addRow("Amount:", amt_row)

        exact_row = QHBoxLayout()
        self.use_exact_amount = QCheckBox("Exact amount")
        self.exact_amount = QDoubleSpinBox()
        self.exact_amount.setRange(0, 9_999_999)
        self.exact_amount.setDecimals(2)
        self.exact_amount.setPrefix("$")
        self.exact_amount.setEnabled(False)
        self.use_exact_amount.toggled.connect(self.exact_amount.setEnabled)
        self.use_exact_amount.toggled.connect(self._toggle_exact_mode)
        exact_row.addWidget(self.use_exact_amount)
        exact_row.addWidget(self.exact_amount)
        exact_row.addStretch()
        nf.addRow("", exact_row)

        cn_row = QHBoxLayout()
        self.check_number_spin = QSpinBox()
        self.check_number_spin.setRange(0, 999_999)
        self.use_check_number = QCheckBox("Filter by check #")
        self.check_number_spin.setEnabled(False)
        self.use_check_number.toggled.connect(self.check_number_spin.setEnabled)
        cn_row.addWidget(self.check_number_spin)
        cn_row.addWidget(self.use_check_number)
        nf.addRow("Check #:", cn_row)
        num_box.setLayout(nf)
        layout.addWidget(num_box)

        date_box = QGroupBox("Date range")
        df = QFormLayout()
        from_row = QHBoxLayout()
        self.use_date_from = QCheckBox("Enable")
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        self.date_from.setEnabled(False)
        self.use_date_from.toggled.connect(self.date_from.setEnabled)
        from_row.addWidget(self.use_date_from)
        from_row.addWidget(self.date_from)
        df.addRow("From:", from_row)
        to_row = QHBoxLayout()
        self.use_date_to = QCheckBox("Enable")
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setEnabled(False)
        self.use_date_to.toggled.connect(self.date_to.setEnabled)
        to_row.addWidget(self.use_date_to)
        to_row.addWidget(self.date_to)
        df.addRow("To:", to_row)
        date_box.setLayout(df)
        layout.addWidget(date_box)

        status_box = QGroupBox("Cleared status")
        sl = QHBoxLayout()
        self.cleared_combo = QComboBox()
        self.cleared_combo.addItems(["Any", "Cleared only", "Uncleared only"])
        sl.addWidget(self.cleared_combo)
        sl.addStretch()
        status_box.setLayout(sl)
        layout.addWidget(status_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def params(self) -> dict:
        p = {}
        if t := self.global_input.text().strip():
            p["text"] = t
        if t := self.payee_input.text().strip():
            p["payee"] = t
        if t := self.drawer_input.text().strip():
            p["drawer"] = t
        if t := self.drawee_input.text().strip():
            p["drawee"] = t
        if t := self.routing_input.text().strip():
            p["routing"] = t
        if t := self.memo_input.text().strip():
            p["memo"] = t
        if t := self.account_input.text().strip():
            p["account"] = t

        if self.use_exact_amount.isChecked():
            val = self.exact_amount.value()
            if val > 0:
                p["amount_min"] = val
                p["amount_max"] = val
        else:
            if self.amount_min.value() > 0:
                p["amount_min"] = self.amount_min.value()
            if self.use_amount_max.isChecked():
                p["amount_max"] = self.amount_max.value()

        if self.use_check_number.isChecked():
            p["check_number"] = self.check_number_spin.value()

        if self.use_date_from.isChecked():
            qd = self.date_from.date()
            p["date_from"] = pydate(qd.year(), qd.month(), qd.day())
        if self.use_date_to.isChecked():
            qd = self.date_to.date()
            p["date_to"] = pydate(qd.year(), qd.month(), qd.day())

        idx = self.cleared_combo.currentIndex()
        if idx == 1:
            p["cleared"] = True
        elif idx == 2:
            p["cleared"] = False

        return p
