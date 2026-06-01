from sqlalchemy import Column, Integer, String, Boolean, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from typing import Dict, Any

Base = declarative_base()


class Check(Base):
    __tablename__ = "checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    check_number = Column(Integer, nullable=False)
    cleared = Column(Boolean, default=False)
    payee = Column(String, nullable=False)
    drawer = Column(String)
    drawee = Column(String)
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)
    account = Column(String)
    routing = Column(String)
    memo = Column(String)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "check_number": self.check_number,
            "cleared": self.cleared,
            "payee": self.payee,
            "drawer": self.drawer,
            "drawee": self.drawee,
            "amount": self.amount,
            "date": self.date.isoformat() if self.date else "",
            "account": self.account,
            "routing": self.routing,
            "memo": self.memo,
        }
