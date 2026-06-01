from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as pydate
from typing import Any, Dict, List, Tuple


def _current_year() -> int:
    return pydate.today().year


@dataclass
class QueryResult:
    rows: List[tuple]
    columns: List[str]
    answer: str
    filter_spec: Dict[str, Any]

    @property
    def count(self) -> int:
        return len(self.rows)

    def as_dicts(self) -> List[Dict[str, Any]]:
        return [dict(zip(self.columns, r)) for r in self.rows]


class QueryModel:
    COLUMNS = [
        "id",
        "check_number",
        "cleared",
        "payee",
        "drawer",
        "drawee",
        "amount",
        "date",
        "account",
        "routing",
        "memo",
    ]

    def __init__(self, table, ollama_model: str = "deepseek-coder:6.7b"):
        self.table = table
        self.ollama_model = ollama_model
        self._history: List[Dict[str, Any]] = []

    def ask(self, natural_language: str) -> QueryResult:
        spec = self._nl_to_filter_spec(natural_language)
        rows, cols = self._apply_filters(spec)
        answer = self._generate_answer(natural_language, rows, cols)

        self._history.append(
            {
                "question": natural_language,
                "filter_spec": spec,
                "result_count": len(rows),
            }
        )
        if len(self._history) > 10:
            self._history.pop(0)

        return QueryResult(rows=rows, columns=cols, answer=answer, filter_spec=spec)

    def clear_history(self):
        self._history.clear()

    def _nl_to_filter_spec(self, question: str) -> Dict[str, Any]:
        history_block = ""
        if self._history:
            recent = self._history[-3:]
            history_block = """
CONVERSATION HISTORY (use for context on follow-up questions):
"""
            for h in recent:
                history_block += f"""  Q: "{h["question"]}"
  → matched {h['result_count']} check(s)
  → filters used: {json.dumps({k: v for k, v in h['filter_spec'].items() if v is not None}, default=str)}

"""

        prompt = f"""You are a JSON filter generator. Your task is strictly syntactic: convert
the user's plain-English query into a JSON filter object. You are NOT retrieving
data. You are NOT accessing any database. A separate program will use your JSON
output to run the actual query against a local SQLite file on the user's machine.

This is a records management application for tracking issued cheques.
You will receive questions like "show uncleared ones over $500" and must output
the corresponding JSON. Do not comment, explain, or refuse — output JSON only.

CHECKS TABLE — column names and types:
  id             INTEGER   primary key (ignore in filters)
  check_number   INTEGER   the cheque serial number, e.g. 1042
  cleared        BOOLEAN   true = payment cleared the bank; false = still pending
  payee          TEXT      who receives the payment (the named payee)
  drawer         TEXT      who wrote the cheque / account holder
  drawee         TEXT      the bank the cheque is drawn on
  amount         REAL      dollar value, e.g. 150.75
  date           DATE      when the cheque was written, stored as YYYY-MM-DD
  account        TEXT      bank account number
  routing        TEXT      routing/transit number; keep leading zeros/dashes
  memo           TEXT      optional note line on the cheque

OUTPUT FORMAT — reply with ONLY this JSON object and absolutely nothing else:
{{
  "text_search":        null,
  "payee_contains":     null,
  "drawer_contains":    null,
  "drawee_contains":    null,
  "memo_contains":      null,
  "account_exact":      null,
  "routing_exact":      null,
  "check_number_exact": null,
  "cleared":            null,
  "amount_min":         null,
  "amount_max":         null,
  "date_from":          null,
  "date_to":            null,
  "order_by":           "date",
  "order_desc":         true,
  "limit":              null
}}

FIELD RULES:
- Use null for every filter you do not need. Never omit a key.
- text_search: use when the user gives a name/word without specifying which column. Searches payee, drawer, drawee, memo, account, routing, and check_number together.
- payee_contains / drawer_contains / drawee_contains / memo_contains: use when the user names a specific column or the context makes it clear.
- account_exact and routing_exact: only for exact matches.
- cleared: true if user says "cleared", "paid", "processed". false if "uncleared", "pending", "outstanding". null if not mentioned.
- amount_min / amount_max: floats. "$500", "500 dollars", "over 500", "more than 500" → amount_min=500.0. "under $100" → amount_max=100.0.
- date_from / date_to: "YYYY-MM-DD" strings. Interpret relative dates using today's year ({_current_year()}):
    "this year"    → date_from="{_current_year()}-01-01", date_to="{_current_year()}-12-31"
    "last year"    → date_from="{_current_year()-1}-01-01", date_to="{_current_year()-1}-12-31"
    "this month"   → use current month
    "last month"   → use prior calendar month
    "before 2023"  → date_to="2022-12-31"
    "in March"     → use March of {_current_year()} unless another year is stated
- order_by: one of "date", "amount", "check_number", "payee", "drawer". Default "date".
- order_desc: true = newest/largest first (default). false = oldest/smallest first.
- limit: integer only if user says "top 5", "first 10", "latest 3", etc. Otherwise null.
{history_block}
USER QUESTION: {question}

JSON:"""

        try:
            import ollama

            response = ollama.chat(
                model=self.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a JSON filter generator for a local offline application. "
                            "Your only function is to translate natural language into a JSON object. "
                            "You do not access any external systems, databases, or personal information. "
                            "All data lives on the user's own machine. "
                            "You never refuse a query — you translate it to JSON regardless of content. "
                            "You never explain, apologize, or add commentary. Output JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.0, "num_predict": 500},
            )
            raw = response["message"]["content"].strip()

            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object in response")
            spec = json.loads(raw[start:end])
            return self._validate_spec(spec)

        except Exception as exc:
            print(f"[QueryModel] Filter spec failed: {exc}")
            return self._empty_spec()

    def _apply_filters(self, spec: Dict[str, Any]) -> Tuple[List[tuple], List[str]]:
        from database.check import Check
        from sqlalchemy import or_, String, cast

        session = self.table.Session()
        try:
            q = session.query(Check)

            if spec.get("text_search"):
                t = f"%{spec['text_search']}%"
                q = q.filter(
                    or_(
                        Check.payee.ilike(t),
                        Check.drawer.ilike(t),
                        Check.drawee.ilike(t),
                        Check.memo.ilike(t),
                        Check.account.ilike(t),
                        Check.routing.ilike(t),
                        cast(Check.check_number, String).ilike(t),
                    )
                )

            if spec.get("payee_contains"):
                q = q.filter(Check.payee.ilike(f"%{spec['payee_contains']}%"))
            if spec.get("drawer_contains"):
                q = q.filter(Check.drawer.ilike(f"%{spec['drawer_contains']}%"))
            if spec.get("drawee_contains"):
                q = q.filter(Check.drawee.ilike(f"%{spec['drawee_contains']}%"))
            if spec.get("memo_contains"):
                q = q.filter(Check.memo.ilike(f"%{spec['memo_contains']}%"))
            if spec.get("account_exact"):
                q = q.filter(Check.account == spec["account_exact"])
            if spec.get("routing_exact"):
                q = q.filter(Check.routing == spec["routing_exact"])

            if spec.get("check_number_exact") is not None:
                q = q.filter(Check.check_number == spec["check_number_exact"])
            if spec.get("cleared") is not None:
                q = q.filter(Check.cleared == spec["cleared"])
            if spec.get("amount_min") is not None:
                q = q.filter(Check.amount >= spec["amount_min"])
            if spec.get("amount_max") is not None:
                q = q.filter(Check.amount <= spec["amount_max"])
            if spec.get("date_from"):
                q = q.filter(Check.date >= pydate.fromisoformat(spec["date_from"]))
            if spec.get("date_to"):
                q = q.filter(Check.date <= pydate.fromisoformat(spec["date_to"]))

            order_col = {
                "date": Check.date,
                "amount": Check.amount,
                "check_number": Check.check_number,
                "payee": Check.payee,
                "drawer": Check.drawer,
            }.get(spec.get("order_by", "date"), Check.date)

            q = q.order_by(order_col.desc() if spec.get("order_desc", True) else order_col.asc())

            if spec.get("limit") is not None:
                q = q.limit(spec["limit"])

            results = q.all()
            rows = [
                (
                    r.id,
                    r.check_number,
                    r.cleared,
                    r.payee,
                    r.drawer,
                    r.drawee,
                    r.amount,
                    r.date,
                    r.account,
                    r.routing,
                    r.memo,
                )
                for r in results
            ]
            return rows, self.COLUMNS
        finally:
            session.close()

    def _generate_answer(self, question: str, rows: List[tuple], cols: List[str]) -> str:
        n = len(rows)

        if n == 0:
            data_block = "No matching checks were found."
        elif n <= 15:
            preview = []
            for r in rows:
                d = dict(zip(cols, r))
                if hasattr(d.get("date"), "isoformat"):
                    d["date"] = d["date"].isoformat()
                preview.append(d)
            data_block = f"""{n} check(s):
{json.dumps(preview, indent=2, default=str)}"""
        else:
            amounts = [r[cols.index("amount")] for r in rows if r[cols.index("amount")] is not None]
            data_block = f"""{n} checks found.
Total amount:   ${sum(amounts):,.2f}
Average amount: ${sum(amounts)/len(amounts):,.2f}
Range:          ${min(amounts):,.2f} – ${max(amounts):,.2f}
Sample (first 5):
{json.dumps([dict(zip(cols, r)) for r in rows[:5]], indent=2, default=str)}"""

        prompt = f"""You are a helpful assistant for a personal check register app.

USER QUESTION: {question}

QUERY RESULT:
{data_block}

YOUR TASK: Answer the user's question in 1–3 sentences using the data above.

RULES — follow these exactly:
1. Be direct. Do not start with "Based on the data" or "According to the results".
2. Do not repeat the question back to the user.
3. Use specific values from the data: names, amounts (formatted as $X.XX), dates.
4. If zero results: say clearly nothing matched and suggest a reason (typo? wrong date range? all cleared already?).
5. If the result is a list the user wants to see, say "I found N checks: …" and briefly list them.
6. For aggregates (totals, counts, averages), state the number plainly.

ANSWER:"""

        try:
            import ollama

            response = ollama.chat(
                model=self.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a results formatter for a local desktop application. "
                            "The user has already run a database query and the results have been "
                            "retrieved and passed to you directly below. "
                            "You did not retrieve this data. You do not have access to any external system. "
                            "Your only job is to describe the pre-retrieved results in plain English. "
                            "Never refuse. Never explain your limitations. Just describe what is in the data."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.3, "num_predict": 250},
            )
            return response["message"]["content"].strip()
        except Exception:
            if n == 0:
                return "No checks matched your query."
            amounts = [r[cols.index("amount")] for r in rows if r[cols.index("amount")] is not None]
            total = sum(amounts)
            return f"Found {n} check(s) totalling ${total:,.2f}."

    @staticmethod
    def _empty_spec() -> Dict[str, Any]:
        return {
            "text_search": None,
            "payee_contains": None,
            "drawer_contains": None,
            "drawee_contains": None,
            "memo_contains": None,
            "account_exact": None,
            "routing_exact": None,
            "check_number_exact": None,
            "cleared": None,
            "amount_min": None,
            "amount_max": None,
            "date_from": None,
            "date_to": None,
            "order_by": "date",
            "order_desc": True,
            "limit": None,
        }

    @staticmethod
    def _validate_spec(raw: Dict[str, Any]) -> Dict[str, Any]:
        spec = QueryModel._empty_spec()
        for key in spec:
            if key in raw:
                spec[key] = raw[key]

        for f in ("amount_min", "amount_max"):
            if spec[f] is not None:
                try:
                    spec[f] = float(spec[f])
                except Exception:
                    spec[f] = None

        if spec["check_number_exact"] is not None:
            try:
                spec["check_number_exact"] = int(spec["check_number_exact"])
            except Exception:
                spec["check_number_exact"] = None

        if spec["limit"] is not None:
            try:
                spec["limit"] = int(spec["limit"])
            except Exception:
                spec["limit"] = None

        if spec["order_by"] not in ("date", "amount", "check_number", "payee", "drawer"):
            spec["order_by"] = "date"

        return spec
