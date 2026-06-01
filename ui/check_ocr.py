from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt


class CheckOCRMixin:

    def automatic_addition(self):
        from models.OCR_model import OCRModel

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Check Image or PDF",
            "",
            "Images & PDF (*.png *.jpg *.jpeg *.tiff *.bmp *.pdf);;All Files (*)"
        )
        if not file_path:
            return

        try:
            model = OCRModel()
        except RuntimeError as exc:
            QMessageBox.critical(self, "OCR Unavailable", str(exc))
            return

        progress = QProgressDialog("Processing check image…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            results = model.extract_all(file_path)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, "OCR Error", f"Failed to process file:\n{exc}")
            import traceback
            traceback.print_exc()
            return

        progress.close()

        if not results:
            QMessageBox.warning(self, "No Results", "No check data could be extracted.")
            return

        # Ask user for cleared status (this value will be used for all imported checks)
        if len(results) == 1:
            cleared = self._ask_cleared()
        else:
            cleared = self._ask_cleared_for_pdf(len(results))
        if cleared is None:
            return

        # Split results into high‑confidence (auto‑import) and low‑confidence (may need review)
        high_conf_results = []
        low_conf_results = []
        for r in results:
            if r.get("needs_manual_review", False):
                low_conf_results.append(r)
            else:
                high_conf_results.append(r)

        # 1. Auto‑import high‑confidence checks
        if high_conf_results:
            self._bulk_ocr_import(high_conf_results, cleared)   # No model parameter

        # 2. Handle low‑confidence checks
        if low_conf_results:
            if len(low_conf_results) == 1:
                # Single low‑confidence check: open review window immediately
                self._open_ocr_review(low_conf_results[0], file_path, cleared=cleared)
            else:
                # Multiple low‑confidence checks: ask user what to do
                reply = QMessageBox.question(
                    self, f"{len(low_conf_results)} Pages Need Review",
                    f"{len(low_conf_results)} of the {len(results)} page(s) have low‑confidence data.\n\n"
                    "• Yes — review each low‑confidence page individually\n"
                    "• No  — auto‑import all (you can edit them later from the table)",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                if reply == QMessageBox.Cancel:
                    return
                elif reply == QMessageBox.Yes:
                    # Queue them for sequential review
                    self._ocr_queue = list(low_conf_results)
                    self._ocr_file_path = file_path
                    self._ocr_total = len(low_conf_results)
                    self._current_ocr_cleared = cleared
                    self._advance_ocr_queue()
                else:   # No → auto‑import all low‑confidence checks as‑is
                    self._bulk_ocr_import(low_conf_results, cleared)

        # 3. If only high‑confidence checks were imported (no low ones), show a completion message
        if high_conf_results and not low_conf_results:
            QMessageBox.information(self, "Import Complete", f"{len(high_conf_results)} check(s) auto‑imported.")
            self.refresh_all()


    def _open_ocr_review(self, result: dict, image_path: str, page_label: str = "", cleared: bool = False):
        from .manual_add_window import ManualAddWindow

        if result.get("error"):
            QMessageBox.warning(
                self, "OCR Warning",
                f"Extraction had errors:\n{result['error']}\n\n"
                "You can still review and fill in missing fields manually."
            )

        fields = result.get("fields", {})

        def fv(name: str) -> str:
            obj = fields.get(name, {})
            val = obj.get("value") if isinstance(obj, dict) else None
            return str(val).strip() if val else ""

        data = {
            "check_number": fv("check_number"),
            "payee": fv("payee"),
            "drawer": fv("drawer"),
            "drawee": fv("drawee"),
            "amount": fv("amount"),
            "date": fv("date_issued"),
            "account": fv("account"),
            "routing": fv("routing"),
            "memo": fv("memo"),
            "cleared": cleared,
        }

        if result.get("needs_manual_review"):
            QMessageBox.information(
                self, "Review Recommended",
                "Some fields have low confidence. Please check the form carefully before saving."
            )

        win = ManualAddWindow(self, self.table, data=data, image_path=image_path)
        if page_label:
            win.setWindowTitle(f"{win.windowTitle()} — {page_label}")

        self._current_manual_window = win

        def on_closed():
            self.refresh_all()
            if hasattr(self, "_ocr_queue") and self._ocr_queue is not None:
                self._advance_ocr_queue()
            self._current_manual_window = None

        win.setAttribute(Qt.WA_DeleteOnClose)
        win.destroyed.connect(on_closed)
        win.show()

    def _advance_ocr_queue(self):
        if not getattr(self, "_ocr_queue", None):
            return

        result = self._ocr_queue.pop(0)
        done = self._ocr_total - len(self._ocr_queue)
        label = f"Page {done} of {self._ocr_total}"
        cleared = getattr(self, "_current_ocr_cleared", False)

        if result.get("error") and not result.get("fields"):
            skip = QMessageBox.question(
                self, f"Error on {label}",
                f"OCR failed for this page:\n{result['error']}\n\nSkip it?",
                QMessageBox.Yes | QMessageBox.No
            )
            if skip == QMessageBox.Yes:
                self._advance_ocr_queue()
                return

        self._open_ocr_review(result, self._ocr_file_path, page_label=label, cleared=cleared)

    def _bulk_ocr_import(self, results: list, cleared: bool):
        """Insert multiple OCR results directly into the database."""
        from database.check import Check
        from datetime import datetime

        session = self.table.Session()
        imported = 0
        errors = []

        try:
            for idx, result in enumerate(results, start=1):
                try:
                    fields = result.get("fields", {})
                    check_data = {}

                    # Extract field values (OCR returns dicts like {"value": "...", "confidence": ...})
                    for field_name in ["check_number", "payee", "drawer", "drawee",
                                    "amount", "date_issued", "account", "routing", "memo"]:
                        val = fields.get(field_name)
                        if isinstance(val, dict):
                            val = val.get("value")
                        if val is not None and str(val).strip():
                            check_data[field_name] = val

                    # Convert date_issued → date
                    if "date_issued" in check_data:
                        try:
                            check_data["date"] = datetime.strptime(check_data["date_issued"], "%Y-%m-%d").date()
                        except Exception:
                            check_data["date"] = None
                        del check_data["date_issued"]

                    # Convert amount to float
                    if "amount" in check_data:
                        try:
                            check_data["amount"] = float(check_data["amount"])
                        except Exception:
                            check_data["amount"] = 0.0

                    # Convert check_number to int
                    if "check_number" in check_data:
                        try:
                            check_data["check_number"] = int(check_data["check_number"])
                        except Exception:
                            check_data["check_number"] = None

                    # Add the user-provided cleared flag
                    check_data["cleared"] = cleared

                    # Create and add the Check object
                    check = Check(**check_data)
                    session.add(check)
                    imported += 1

                except Exception as e:
                    errors.append(f"Page {idx}: {e}")

            session.commit()

        finally:
            session.close()

        self.refresh_all()
        msg = f"Imported {imported} of {len(results)} check(s)."
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors)
        QMessageBox.information(self, "Import Complete", msg)



    def _ask_cleared(self, page_label: str = "") -> Optional[bool]:
        text = f"{page_label}\n\nHas this check been cleared?" if page_label else "Has this check been cleared?"
        
        # Use the static question method and explicit StandardButton enums
        reply = QMessageBox.question(
            self,
            "Check Cleared Status",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.NoButton
        )
        
        # Strictly compare against the StandardButton enum type
        if reply == QMessageBox.StandardButton.Yes:
            return True
        elif reply == QMessageBox.StandardButton.No:
            return False
        else:
            return None

    def _ask_cleared_for_pdf(self, num_checks: int) -> Optional[bool]:
        reply = QMessageBox.question(
            self,
            "Cleared Status",
            f"This PDF contains {num_checks} cheque(s).\n\nAre they all cleared?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.NoButton
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            return True
        elif reply == QMessageBox.StandardButton.No:
            return False
        else:
            return None

