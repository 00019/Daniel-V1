from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from .dialogs.query_dialog import QueryDialog

from chats.query_chats import QueryModel


class CheckQueryMixin:

    def open_query_dialog(self):
        dlg = QueryDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        rows, cols = self.table.query_checks(**dlg.params())
        idx = {name: i for i, name in enumerate(cols)}

        converted = []
        for r in rows:
            converted.append((
                self._to_int(r[idx["id"]]),
                self._to_int(r[idx["check_number"]]),
                self._to_bool(r[idx["cleared"]]),
                self._to_str(r[idx["payee"]]),
                self._to_str(r[idx["drawer"]]),
                self._to_str(r[idx["drawee"]]),
                self._to_float(r[idx["amount"]]),
                self._to_date(r[idx["date"]]),
                self._to_str(r[idx["account"]]),
                self._to_str(r[idx["routing"]]),
                self._to_str(r[idx["memo"]]),
            ))

        self.query_active = True
        self.query_rows = converted
        self._update_display_button_text()
        self.load_checks()

    def clear_query(self):
        self.query_active = False
        self.query_rows = None
        self._update_display_button_text()
        self.load_checks()

    def manual_query(self):
        self.open_query_dialog()

    def assisted_query(self):
        question, ok = QInputDialog.getText(
            self,
            "Assisted Query",
            "Ask a question about your checks:"
        )
        if not ok or not question.strip():
            return
        
        model = QueryModel(self.table)
        result = model.ask(question)
        self.query_active = True
        self.query_rows = result.rows
        self._update_display_button_text()
        self.load_checks()
        QMessageBox.information(self, "Query Result", result.answer)

