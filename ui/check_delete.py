from PySide6.QtWidgets import QMessageBox

from database.table import Table


class CheckDeleteMixin:

    def delete_check(self):
        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            QMessageBox.warning(self, "No Selection", "Please select a check to delete")
            return
        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a check to delete")
            return
        row = selected_rows[0].row()
        model = self.table_view.model()
        if model is None:
            QMessageBox.critical(self, "Error", "No table model is loaded.")
            return
        raw_id = model.index(row, self.FIELD_TO_COL["id"]).data()
        try:
            check_id = int(raw_id)
        except Exception:
            QMessageBox.critical(self, "Error", "Could not read hidden ID for selected row.")
            return
        confirm = QMessageBox.question(self, "Confirm Delete", f"Delete check ID {check_id}?")
        if confirm != QMessageBox.Yes:
            return
        target_row = None
        for i, c in enumerate(Table.checks):
            if c.get("id") == check_id:
                target_row = i
                break
        if target_row is None:
            QMessageBox.critical(self, "Error", "Could not locate the selected check in memory.")
            return
        self.table.delete_check(target_row)
        self.clear_query()

    def delete_selected_checks(self):
        selection_model = self.table_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            QMessageBox.warning(self, "No Selection", "Please select at least one check to delete.")
            return
        selected_rows = sorted(set([idx.row() for idx in selection_model.selectedRows()]))
        if not selected_rows:
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(selected_rows)} selected check(s)?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        model = self.table_view.model()
        if not model:
            return
        ids_to_delete = []
        for row in selected_rows:
            idx = model.index(row, self.FIELD_TO_COL["id"])
            raw_id = idx.data()
            try:
                check_id = int(raw_id)
                ids_to_delete.append(check_id)
            except Exception:
                pass
        if not ids_to_delete:
            QMessageBox.critical(self, "Error", "Could not retrieve IDs for selected rows.")
            return
        rows_to_delete = []
        for i, c in enumerate(Table.checks):
            if c.get("id") in ids_to_delete:
                rows_to_delete.append(i)
        for row_idx in sorted(rows_to_delete, reverse=True):
            self.table.delete_check(row_idx)
        self.refresh_all()
        QMessageBox.information(self, "Delete Complete", f"Deleted {len(rows_to_delete)} check(s).")

    def delete_shown_checks(self):
        model = self.table_view.model()
        if not model or model.rowCount() == 0:
            QMessageBox.warning(self, "Nothing to Delete", "No checks are currently shown.")
            return
        count = model.rowCount()
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete all {count} displayed check(s)?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        ids_to_delete = []
        for row in range(count):
            idx = model.index(row, self.FIELD_TO_COL["id"])
            raw_id = idx.data()
            try:
                check_id = int(raw_id)
                ids_to_delete.append(check_id)
            except Exception:
                pass
        if not ids_to_delete:
            QMessageBox.critical(self, "Error", "Could not retrieve IDs for displayed checks.")
            return
        rows_to_delete = []
        for i, c in enumerate(Table.checks):
            if c.get("id") in ids_to_delete:
                rows_to_delete.append(i)
        for row_idx in sorted(rows_to_delete, reverse=True):
            self.table.delete_check(row_idx)
        self.refresh_all()
        QMessageBox.information(self, "Delete Complete", f"Deleted {len(rows_to_delete)} check(s).")
