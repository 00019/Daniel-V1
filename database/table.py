from sortedcontainers import SortedList
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from database.check import Base, Check


class Table:
    db_path: str = ""
    checks: SortedList = SortedList(key=lambda x: (-x["date"].toordinal(), -x["id"]))

    def __init__(self, path: str):
        Table.db_path = path
        self.engine = create_engine(f"sqlite:///{Table.db_path}")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.Session = Session
        Table.checks.clear()

    def create_table(self):
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _row_from_check(check: Check) -> Dict[str, Any]:
        return {
            "id": check.id,
            "check_number": check.check_number,
            "cleared": check.cleared,
            "payee": check.payee,
            "drawer": getattr(check, "drawer", "") or "",
            "drawee": getattr(check, "drawee", "") or "",
            "amount": check.amount,
            "date": check.date,
            "account": getattr(check, "account", "") or "",
            "routing": getattr(check, "routing", "") or "",
            "memo": getattr(check, "memo", "") or "",
        }

    def load_from_db(self):
        session = self.Session()
        try:
            Table.checks.clear()
            for check in session.query(Check).all():
                Table.checks.add(self._row_from_check(check))
        except Exception as e:
            print(f"Error loading from database: {e}")
        finally:
            session.close()

    def load_into_db(self):
        session = self.Session()
        try:
            session.query(Check).delete()
            for check_data in Table.checks:
                check = Check(
                    id=check_data.get("id"),
                    check_number=check_data.get("check_number", 0),
                    cleared=check_data.get("cleared", False),
                    payee=check_data.get("payee", ""),
                    drawer=check_data.get("drawer", ""),
                    drawee=check_data.get("drawee", ""),
                    amount=check_data.get("amount", 0.0),
                    date=check_data.get("date", date.today()),
                    account=check_data.get("account", ""),
                    routing=check_data.get("routing", ""),
                    memo=check_data.get("memo", ""),
                )
                session.add(check)
            session.commit()
            print(f"Successfully loaded {len(Table.checks)} checks into database")
        except Exception as e:
            print(f"Error loading into database: {e}")
            session.rollback()
        finally:
            session.close()

    def order_by(self, primary_attr: str = "date", ascending: bool = False):
        if not Table.checks:
            return
        if primary_attr not in Table.checks[0]:
            raise ValueError(f"Invalid attribute: {primary_attr}")
        first_value = Table.checks[0][primary_attr]
        if not isinstance(first_value, (int, float, date)):
            raise ValueError(
                f"Cannot sort by attribute '{primary_attr}'. Only numeric types (int, float) and dates are supported."
            )

        def create_sort_key(attr, asc):
            if isinstance(first_value, date):
                if asc:
                    return lambda x: (x[attr].toordinal() if x[attr] is not None else float("-inf"), x["id"])
                return lambda x: (-x[attr].toordinal() if x[attr] is not None else float("inf"), -x["id"])
            if asc:
                return lambda x: (x[attr] if x[attr] is not None else float("-inf"), x["id"])
            return lambda x: (-x[attr] if x[attr] is not None else float("inf"), -x["id"])

        key = create_sort_key(primary_attr, ascending)
        Table.checks = SortedList(list(Table.checks), key=key)

    def add_check(self, check_json: Dict[str, Any]):
        session = self.Session()
        try:
            max_id = max((check["id"] for check in Table.checks), default=0)
            next_id = max_id + 1
            check_data = {
                "id": next_id,
                "check_number": check_json.get("check_number", 0),
                "cleared": check_json.get("cleared", False),
                "payee": check_json.get("payee", ""),
                "drawer": check_json.get("drawer", ""),
                "drawee": check_json.get("drawee", ""),
                "amount": check_json.get("amount", 0.0),
                "date": check_json.get("date", date.today()),
                "account": check_json.get("account", ""),
                "routing": check_json.get("routing", ""),
                "memo": check_json.get("memo", ""),
            }
            Table.checks.add(check_data)
            session.add(Check(**check_data))
            session.commit()
            return next_id
        except Exception as e:
            print(f"Error adding check: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def delete_check(self, row_number: int):
        session = self.Session()
        try:
            check_data = Table.checks[row_number]
            check_id = check_data["id"]
            del Table.checks[row_number]
            session.query(Check).filter(Check.id == check_id).delete()
            session.commit()
            print(f"Successfully deleted check ID {check_id} from row {row_number}")
        except IndexError:
            print(f"Row number {row_number} not found - only {len(Table.checks)} rows available")
        except Exception as e:
            print(f"Error deleting check: {e}")
            session.rollback()
        finally:
            session.close()

    def modify_check(self, row_number: int, modification):
        session = self.Session()
        try:
            original_data = dict(Table.checks[row_number])
            check_id = original_data["id"]
            if isinstance(modification, dict):
                for key, value in modification.items():
                    if key != "id":
                        original_data[key] = value
            else:
                attr, value = modification
                if attr != "id":
                    original_data[attr] = value
            del Table.checks[row_number]
            Table.checks.add(original_data)
            db_check = session.query(Check).filter(Check.id == check_id).first()
            if db_check:
                if isinstance(modification, dict):
                    for key, value in modification.items():
                        if key != "id" and hasattr(db_check, key):
                            setattr(db_check, key, value)
                else:
                    attr, value = modification
                    if attr != "id" and hasattr(db_check, attr):
                        setattr(db_check, attr, value)
                session.commit()
                print(f"Successfully modified check ID {check_id}")
        except IndexError:
            print(f"Row number {row_number} not found - only {len(Table.checks)} rows available")
        except Exception as e:
            print(f"Error modifying check: {e}")
            session.rollback()
        finally:
            session.close()

    def query_checks(
        self,
        *,
        primary_id: Optional[int] = None,
        payee: Optional[str] = None,
        drawer: Optional[str] = None,
        drawee: Optional[str] = None,
        memo: Optional[str] = None,
        account: Optional[str] = None,
        routing: Optional[str] = None,
        cleared: Optional[bool] = None,
        check_number: Optional[int] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        text: Optional[str] = None,
        case_insensitive: bool = True,
        limit: Optional[int] = None,
    ) -> Tuple[List[tuple], List[str]]:
        columns = [
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

        def norm(s: str) -> str:
            return s.lower() if case_insensitive else s

        def contains(hay: Any, needle: str) -> bool:
            if hay is None:
                return False
            return norm(needle) in norm(str(hay))

        results: List[tuple] = []
        n = 0

        for c in Table.checks:
            if primary_id is not None and c.get("id") != primary_id:
                continue
            if check_number is not None and c.get("check_number") != check_number:
                continue
            if cleared is not None and bool(c.get("cleared")) != bool(cleared):
                continue
            if account is not None and c.get("account") != account:
                continue
            if routing is not None and c.get("routing") != routing:
                continue
            if payee is not None and not contains(c.get("payee", ""), payee):
                continue
            if drawer is not None and not contains(c.get("drawer", ""), drawer):
                continue
            if drawee is not None and not contains(c.get("drawee", ""), drawee):
                continue
            if memo is not None and not contains(c.get("memo", ""), memo):
                continue
            amt = c.get("amount")
            if amount_min is not None and (amt is None or amt < amount_min):
                continue
            if amount_max is not None and (amt is None or amt > amount_max):
                continue
            d = c.get("date")
            if date_from is not None and (d is None or d < date_from):
                continue
            if date_to is not None and (d is None or d > date_to):
                continue
            if text:
                if not (
                    contains(c.get("payee", ""), text)
                    or contains(c.get("drawer", ""), text)
                    or contains(c.get("drawee", ""), text)
                    or contains(c.get("memo", ""), text)
                    or contains(c.get("account", ""), text)
                    or contains(c.get("routing", ""), text)
                    or contains(c.get("check_number", ""), text)
                ):
                    continue

            row = (
                c.get("id"),
                c.get("check_number"),
                c.get("cleared"),
                c.get("payee"),
                c.get("drawer"),
                c.get("drawee"),
                c.get("amount"),
                c.get("date"),
                c.get("account"),
                c.get("routing"),
                c.get("memo"),
            )
            results.append(row)
            n += 1
            if limit is not None and n >= limit:
                break

        return results, columns

    def update_check(self, check_id: int, data: Dict[str, Any]):
        session = self.Session()
        try:
            db_check = session.query(Check).filter(Check.id == check_id).first()
            if not db_check:
                return
            for k, v in data.items():
                if hasattr(db_check, k):
                    setattr(db_check, k, v)
            session.commit()
            for c in Table.checks:
                if c.get("id") == check_id:
                    for k, v in data.items():
                        c[k] = v
                    break
        except Exception as e:
            session.rollback()
            print(f"Error updating check: {e}")
        finally:
            session.close()
