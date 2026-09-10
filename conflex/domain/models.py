"""领域实体、值对象与枚举（纯数据，无 IO）。"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class AdjustType(str, Enum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_final(self) -> bool:
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    list_date: date
    delist_date: date | None = None
    board: str = "main"
    is_st: bool = False

    @staticmethod
    def exchange_of(symbol: str) -> str:
        code = symbol.split(".")[0]
        if code.startswith(("60", "68", "11", "13", "50", "51", "56", "58")):
            return "SH"
        if code.startswith(("00", "30", "12", "15", "16", "18")):
            return "SZ"
        if code.startswith(("43", "83", "87", "88", "92")):
            return "BJ"
        return "SH"


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0
    turnover: float | None = None
    pre_close: float | None = None
    suspended: bool = False


@dataclass(frozen=True)
class AdjustFactor:
    symbol: str
    trade_date: date
    factor: float


@dataclass
class Fill:
    order_id: int
    symbol: str
    side: Side
    qty: int
    price: float
    trade_date: date
    commission: float = 0.0
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0

    @property
    def fee(self) -> float:
        return self.commission + self.stamp_tax + self.transfer_fee


def asdict(obj) -> dict:
    """dataclass -> dict，枚举/日期转基础类型。"""

    def _convert(v):
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v

    return {k: _convert(v) for k, v in dataclasses.asdict(obj).items()}
