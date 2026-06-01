import os

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QPushButton, QListWidget,
    QLabel, QFileDialog, QInputDialog, QMessageBox, QHBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt

from database.table import Table
from ui.check_display_window import CheckDisplayWindow


class HomeWindow(QWidget):
    def __init__(self, project_root: str):
        super().__init__()

        self.resize(1250, 600)
        self.databases_dir = os.path.join(project_root, "checks")
        os.makedirs(self.databases_dir, exist_ok=True)

        self.current_check_display_window = None
        self.current_db_path = None
        self.current_table = None

        self.stacked = QStackedWidget(self)

        self._build_home_screen()
        root_layout = QVBoxLayout(self)
        root_layout.addWidget(self.stacked)
        self.setLayout(root_layout)

        self.load_databases()

    def _build_home_screen(self):
        home = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Check Tabulator - Select Database")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        self.db_list = QListWidget()
        self.db_list.itemDoubleClicked.connect(self.on_database_chosen)
        layout.addWidget(QLabel("Available Databases:"))
        layout.addWidget(self.db_list)

        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.clicked.connect(self.load_databases)
        button_layout.addWidget(self.refresh_btn)

        self.create_btn = QPushButton("Create New Database")
        self.create_btn.clicked.connect(self.create_database)
        button_layout.addWidget(self.create_btn)

        self.browse_btn = QPushButton("Browse Other Location")
        self.browse_btn.clicked.connect(self.browse_database)
        button_layout.addWidget(self.browse_btn)

        layout.addLayout(button_layout)

        home.setLayout(layout)
        self.stacked.addWidget(home)

    def load_databases(self):
        self.db_list.clear()
        for file in sorted(os.listdir(self.databases_dir)):
            if file.lower().endswith(".db"):
                self.db_list.addItem(file)

    def on_database_chosen(self, item):
        db_name = item.text()
        db_path = os.path.join(self.databases_dir, db_name)
        self.open_database(db_path)

    def create_database(self):
        name, ok = QInputDialog.getText(self, "Create Database", "Enter database name:")
        if not (ok and name):
            return
        if not name.lower().endswith(".db"):
            name += ".db"
        db_path = os.path.join(self.databases_dir, name)
        if os.path.exists(db_path):
            QMessageBox.warning(self, "Database Exists", f"Database '{name}' already exists!")
            self.open_database(db_path)
            return
        try:
            table = Table(db_path)
            table.create_table()
            self.load_databases()
            self.open_database(db_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create database: {e}")

    def browse_database(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Database File", "", "Database Files (*.db);;All Files (*)"
        )
        if file_path:
            self.open_database(file_path)

    def open_database(self, db_path: str):
        try:
            table = Table(db_path)
            self.current_db_path = db_path
            self.current_table = table
            if self.current_check_display_window is None:
                self.current_check_display_window = CheckDisplayWindow(table, db_path)
                self.current_check_display_window.back_to_home.connect(self.show_home)
                self.stacked.addWidget(self.current_check_display_window)
            else:
                self.current_check_display_window.update_table(table, db_path)
            self.stacked.setCurrentWidget(self.current_check_display_window)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open database: {e}")

    def show_home(self):
        self.stacked.setCurrentIndex(0)
