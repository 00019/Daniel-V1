from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt

from database.table import Table


class CheckStatusMixin:

    def _get_selected_ids(self) -> list:
        model = self.table_view.model()
        if not model:
            return []
        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return []
        ids = []
        for idx in selection_model.selectedRows():
            row = idx.row()
            id_index = model.index(row, self.FIELD_TO_COL["id"])
            try:
                check_id = int(id_index.data())
                ids.append(check_id)
            except (ValueError, TypeError):
                continue
        return ids

    def clear_selected_checks(self):
        self._set_selected_cleared(True)

    def unclear_selected_checks(self):
        self._set_selected_cleared(False)

    def toggle_selected_checks(self):
        self._set_selected_cleared(None)

    def clear_shown_checks(self):
        self._set_shown_cleared(True)

    def unclear_shown_checks(self):
        self._set_shown_cleared(False)

    def toggle_shown_checks(self):
        self._set_shown_cleared(None)

    def _set_selected_cleared(self, target):
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.warning(self, "No Selection", "Please select at least one check.")
            return
        if target is None:
            confirm = QMessageBox.question(self, "Toggle Status", f"Toggle cleared status for {len(ids)} selected check(s)?")
        else:
            label = "CLEARED" if target else "UNCLEARED"
            confirm = QMessageBox.question(self, "Update Status", f"Mark {len(ids)} selected check(s) as {label}?")
        if confirm != QMessageBox.Yes:
            return
        self._update_cleared_by_ids(ids, target)

    def _set_shown_cleared(self, target):
        model = self.table_view.model()
        if not model or model.rowCount() == 0:
            QMessageBox.warning(self, "Nothing to Update", "No checks are currently shown.")
            return
        count = model.rowCount()
        if target is None:
            confirm = QMessageBox.question(self, "Toggle Status", f"Toggle cleared status for all {count} displayed check(s)?")
        else:
            label = "CLEARED" if target else "UNCLEARED"
            confirm = QMessageBox.question(self, "Update Status", f"Mark all {count} displayed check(s) as {label}?")
        if confirm != QMessageBox.Yes:
            return
        ids = []
        for row in range(count):
            idx = model.index(row, self.FIELD_TO_COL["id"])
            try:
                check_id = int(idx.data())
                ids.append(check_id)
            except Exception:
                pass
        self._update_cleared_by_ids(ids, target)

    def _update_cleared_by_ids(self, ids: list, target):
        updated = 0
        for i, c in enumerate(Table.checks):
            if c.get("id") in ids:
                data = c.copy()
                if target is None:
                    data["cleared"] = not data.get("cleared", False)
                else:
                    data["cleared"] = target
                self.table.modify_check(i, data)
                updated += 1
        self.refresh_all()
        action = "Toggled" if target is None else ("Cleared" if target else "Uncleared")
        QMessageBox.information(self, "Update Complete", f"{action} {updated} check(s).")
