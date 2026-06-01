from __future__ import annotations

import base64
import json
import fitz
import io
from PIL import Image   
from datetime import date as pydate
from pathlib import Path
from typing import Any, Dict, List, Optional


class OCRChat:

    FIELDS = ["check_number", "date_issued", "payee", "drawer", "drawee", "amount", "memo", "account", "routing"]
    CRITICAL = ["check_number", "date_issued", "payee", "drawer", "drawee", "amount"]

    _SYSTEM_PROMPT = (
        "You are an expert at reading cheque images. Extract the requested fields accurately and return JSON only.\n\n"
        "FIELD DEFINITIONS:\n"
        "- payee: the person or company being paid (the name on 'Pay to the Order of').\n"
        "- drawer: the person or company that wrote the cheque and owns the account.\n"
        "- drawee: the bank the cheque is drawn on.\n"
        "- amount: the numeric dollar value from the amount box. Return it without $ or commas.\n"
        "- date_issued: the date the cheque was written, in YYYY-MM-DD format.\n"
        "- check_number: the cheque serial number, usually short and near the top or bottom edge.\n"
        "- account: the bank account number. This is not the cheque number and not the routing number.\n"
        "- routing: the routing/transit number. Keep it exactly as printed, including any leading zeros or dashes.\n"
        "- memo: the memo line text, or an empty string if absent.\n\n"
        "COMMON MISTAKES TO AVOID:\n"
        "• Do not swap payee, drawer, and drawee.\n"
        "• Do not confuse the routing number with the account number.\n"
        "• Never invent data. Use null for missing numeric fields and empty string for missing text fields.\n\n"
        "OUTPUT FORMAT:\n"
        "Return only a valid JSON object with exactly these keys: "
        "check_number, date_issued, payee, drawer, drawee, amount, memo, account, routing.\n\n"
        "Example:\n"
        "{\n"
        '  "check_number": "1042",\n'
        '  "date_issued": "2024-03-15",\n'
        '  "payee": "John Smith",\n'
        '  "drawer": "Jane Doe",\n'
        '  "drawee": "Bank of Example",\n'
        '  "amount": "250.00",\n'
        '  "memo": "Rent",\n'
        '  "account": "123456789",\n'
        '  "routing": "000123456"\n'
        "}\n"
    )

    def __init__(self, ollama_model: str = "qwen2.5vl:3b"):
        self.ollama_model = ollama_model
        self._verify_ollama()

    def _verify_ollama(self) -> None:
        try:
            import ollama
            ollama.list()
        except Exception as exc:
            raise RuntimeError(
                f"Ollama is not running or the model '{self.ollama_model}' is unavailable.\n"
                f"Start Ollama and run:  ollama pull {self.ollama_model}\n"
                f"Detail: {exc}"
            ) from exc

    def extract(self, file_path: str) -> Dict[str, Any]:
        result = self._process_image_file(file_path)
        result.setdefault("raw_ocr", None)
        result["needs_manual_review"] = self._needs_review(result.get("fields", {}))
        return result

    def extract_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        doc = fitz.open(pdf_path)
        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=100)
                img_bytes = pix.tobytes(output="jpeg", jpg_quality=85)
                result = self._call_vision(img_bytes, page_num=page_num + 1)
                result["page_num"] = page_num + 1
                result["page_label"] = f"Page {page_num + 1}"
                result["needs_manual_review"] = self._needs_review(result.get("fields", {}))
                results.append(result)
        finally:
            doc.close()
        return results

    def extract_all(self, file_path: str) -> List[Dict[str, Any]]:
        if Path(file_path).suffix.lower() == ".pdf":
            return self.extract_pdf(file_path)
        return [self.extract(file_path)]

    @staticmethod
    def to_check_dict(extracted: Dict[str, Any]) -> Dict[str, Any]:
        fields = extracted.get("fields") or {}

        def v(name: str) -> Optional[str]:
            obj = fields.get(name)
            if not isinstance(obj, dict):
                return None
            val = obj.get("value")
            if val is None or str(val).strip() == "":
                return None
            return str(val).strip()

        cn_s = v("check_number")
        payee_s = v("payee")
        amt_s = v("amount")
        date_s = v("date_issued")

        missing = [k for k, val in [
            ("check_number", cn_s),
            ("payee", payee_s),
            ("amount", amt_s),
            ("date_issued", date_s),
        ] if not val]
        if missing:
            raise ValueError(f"Missing required field(s): {', '.join(missing)}")

        try:
            check_number = int(cn_s)
        except (ValueError, TypeError):
            raise ValueError(f"check_number '{cn_s}' is not a valid integer")

        try:
            amount = float(amt_s.replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            raise ValueError(f"amount '{amt_s}' is not a valid number")

        try:
            y, m, d = date_s.split("-")
            date_obj = pydate(int(y), int(m), int(d))
        except Exception:
            raise ValueError(f"date_issued '{date_s}' must be in YYYY-MM-DD format")

        return {
            "check_number": check_number,
            "cleared": False,
            "payee": payee_s,
            "drawer": v("drawer") or "",
            "drawee": v("drawee") or "",
            "amount": amount,
            "date": date_obj,
            "account": v("account") or "",
            "routing": v("routing") or "",
            "memo": v("memo") or "",
        }

    def impute_to_db(self, table: Any, extracted: Dict[str, Any]) -> int:
        data = OCRModel.to_check_dict(extracted)
        new_id = table.add_check(data)
        if new_id is None:
            raise RuntimeError("table.add_check() returned None — check the database for errors")
        return new_id

    def _process_image_file(self, image_path: str) -> Dict[str, Any]:
        try:
            with open(image_path, "rb") as fh:
                img_bytes = fh.read()
            img_bytes = self._to_jpeg(img_bytes, quality=75, max_size=1024)
            return self._call_vision(img_bytes)
        except Exception as exc:
            return {"error": str(exc), "fields": {}}

    def _call_vision(self, img_bytes: bytes, page_num: int = 0) -> Dict[str, Any]:
        import ollama

        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        try:
            response = ollama.chat(
                model=self.ollama_model,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "Extract the cheque fields from the attached image and return JSON only.",
                        "images": [img_b64],
                    },
                ],
                options={"temperature": 0.0},
            )
            raw = response["message"]["content"]

            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object found in model response")

            data = json.loads(raw[start:end])

            fields: Dict[str, Any] = {}
            for key in self.FIELDS:
                value = data.get(key)
                if value is None or str(value).strip() == "":
                    fields[key] = {"value": None}
                else:
                    fields[key] = {"value": str(value).strip()}
            return {"fields": fields, "error": None}

        except Exception as exc:
            suffix = f" (page {page_num})" if page_num else ""
            return {"error": f"Vision extraction failed{suffix}: {exc}", "fields": {}}

    def _needs_review(self, fields: Dict[str, Any]) -> bool:
        # Returns True if ANY critical field is blank (missing value or empty string)
        for key in self.CRITICAL:
            obj = fields.get(key, {})
            val = obj.get("value") if isinstance(obj, dict) else None
            if val is None or (isinstance(val, str) and val.strip() == ""):
                return True
        return False

    def _to_jpeg(self, img_bytes: bytes, quality: int = 75, max_size: int = 1024) -> bytes:
        img = Image.open(io.BytesIO(img_bytes))

        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            print(f"Resized image from {img.size} to {new_size}")

        if img.mode in ("RGBA", "LA", "P"):
            rgb = Image.new("RGB", img.size, (255, 255, 255))
            rgb.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = rgb

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()