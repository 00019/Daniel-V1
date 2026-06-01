from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QDateEdit, QTextEdit,
    QCheckBox, QPushButton, QLabel, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QPixmap
from database.table import Table
import os


class ManualAddWindow(QWidget):
    check_saved = Signal()

    def __init__(self, parent, table: Table, data: dict = None, image_path: str = None):
        super().__init__()

        self.parent = parent
        self.table = table
        self.image_path = image_path
        self.data = data

        self.is_edit = data is not None and data.get("id") is not None
        self.check_id = data.get("id") if self.is_edit else None

        self.setWindowTitle("Edit Check" if self.is_edit else "Add Check - Manual Entry")
        self.setMinimumWidth(650)

        main_layout = QHBoxLayout()

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)

        self.check_number_input = QLineEdit()
        self.cleared_input = QCheckBox("Cleared")
        self.payee_input = QLineEdit()
        self.drawer_input = QLineEdit()
        self.drawee_input = QLineEdit()
        self.amount_input = QLineEdit()
        self.date_input = QDateEdit(calendarPopup=True)
        self.date_input.setDate(QDate.currentDate())
        self.account_input = QLineEdit()
        self.routing_input = QLineEdit()
        self.memo_input = QTextEdit()
        self.memo_input.setMaximumHeight(100)

        form_layout.addWidget(QLabel("Check Number"))
        form_layout.addWidget(self.check_number_input)
        form_layout.addWidget(self.cleared_input)
        form_layout.addWidget(QLabel("Payee"))
        form_layout.addWidget(self.payee_input)
        form_layout.addWidget(QLabel("Drawer"))
        form_layout.addWidget(self.drawer_input)
        form_layout.addWidget(QLabel("Drawee"))
        form_layout.addWidget(self.drawee_input)
        form_layout.addWidget(QLabel("Amount"))
        form_layout.addWidget(self.amount_input)
        form_layout.addWidget(QLabel("Date Issued"))
        form_layout.addWidget(self.date_input)
        form_layout.addWidget(QLabel("Account"))
        form_layout.addWidget(self.account_input)
        form_layout.addWidget(QLabel("Routing #"))
        form_layout.addWidget(self.routing_input)
        form_layout.addWidget(QLabel("Memo"))
        form_layout.addWidget(self.memo_input)

        done_btn = QPushButton("Done")
        done_btn.clicked.connect(self.save_check)
        form_layout.addWidget(done_btn)

        main_layout.addWidget(form_widget, 2)

        if image_path and os.path.exists(image_path):
            image_widget = QWidget()
            image_layout = QVBoxLayout(image_widget)
            image_label = QLabel("Check Image")
            image_layout.addWidget(image_label)
            self.image_display = QLabel()
            self.image_display.setAlignment(Qt.AlignCenter)
            self.image_display.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
            self.image_display.setMinimumWidth(250)
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(250, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_display.setPixmap(scaled_pixmap)
                self.image_display.setToolTip(f"Check image: {os.path.basename(image_path)}")
            else:
                self.image_display.setText("Failed to load image")
            image_layout.addWidget(self.image_display)
            image_layout.addStretch()
            main_layout.addWidget(image_widget, 1)

        self.setLayout(main_layout)

        if self.data:
            self.check_number_input.setText(str(self.data.get("check_number", "")))
            self.payee_input.setText(self.data.get("payee", ""))
            self.drawer_input.setText(self.data.get("drawer", ""))
            self.drawee_input.setText(self.data.get("drawee", ""))
            self.amount_input.setText(str(self.data.get("amount", "")))
            self.account_input.setText(self.data.get("account", ""))
            self.routing_input.setText(self.data.get("routing", ""))
            self.memo_input.setPlainText(self.data.get("memo", ""))
            self.cleared_input.setChecked(bool(self.data.get("cleared", False)))
            try:
                y, m, d = str(self.data.get("date", "")).split("-")
                self.date_input.setDate(QDate(int(y), int(m), int(d)))
            except Exception:
                pass

    def save_check(self):
        try:
            check_number_text = self.check_number_input.text().strip()
            payee = self.payee_input.text().strip()
            drawer = self.drawer_input.text().strip()
            drawee = self.drawee_input.text().strip()
            amount_text = self.amount_input.text().strip()
            date = self.date_input.date().toPython()
            memo = self.memo_input.toPlainText().strip()
            cleared = self.cleared_input.isChecked()
            account = self.account_input.text().strip()
            routing = self.routing_input.text().strip()

            if not check_number_text:
                raise ValueError("Check number cannot be empty.")
            if not payee:
                raise ValueError("Payee cannot be empty.")
            if not amount_text:
                raise ValueError("Amount cannot be empty.")

            check_number = int(check_number_text)
            amount = float(amount_text.replace("$", "").replace(",", ""))

            data = {
                "check_number": check_number,
                "cleared": cleared,
                "payee": payee,
                "drawer": drawer,
                "drawee": drawee,
                "amount": amount,
                "date": date,
                "account": account,
                "routing": routing,
                "memo": memo,
            }

            if not self.is_edit:
                self.table.add_check(data)
            else:
                if self.check_id is None:
                    raise ValueError("Missing check ID for edit mode.")
                row_index = None
                for i, c in enumerate(Table.checks):
                    if c.get("id") == self.check_id:
                        row_index = i
                        break
                if row_index is None:
                    raise ValueError("Check not found in database.")
                self.table.modify_check(row_index, data)

            self.check_saved.emit()
            self.close()

        except ValueError as ve:
            QMessageBox.warning(self, "Invalid Input", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
