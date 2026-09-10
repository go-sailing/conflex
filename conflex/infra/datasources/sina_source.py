"""新浪财经适配器（免费源，HTTP API，无需额外依赖）。"""
from __future__ import annotations

import json
import urllib.request
from datetime import date
from urllib.parse import urlencode

import pandas as pd

from conflex.infra.datasources.base import BaseDataSource, guarded


class SinaDataSource(BaseDataSource):
    name = "sina"
    COLUMN_MAP = {
        "day": "trade_date", "volume": "volume",
    }

    _BASE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    def __init__(self):
        super().__init__()

    @staticmethod
    def _to_sina_code(symbol: str) -> str:
        """sh600519 / sz000001 格式。"""
        parts = symbol.split(".")
        if len(parts) == 2:
            code, market = parts
            return f"{market.lower()}{code}"
        code = symbol
        if code.startswith(("6", "9")):
            return f"sh{code}"
        return f"sz{code}"

    def _fetch_json(self, params: dict) -> list:
        url = f"{self._BASE_URL}?{urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    @guarded
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        sina_code = self._to_sina_code(symbol)
        days_span = (end - start).days + 30
        datalen = min(max(days_span, 1000), 1023)

        data = self._fetch_json({
            "symbol": sina_code,
            "scale": 240,
            "ma": "no",
            "datalen": datalen,
        })

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df = df.rename(columns={"day": "trade_date"})
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["symbol"] = symbol
        df = df[(df["trade_date"].dt.date >= start) & (df["trade_date"].dt.date <= end)]
        return df[["symbol", "trade_date", "open", "high", "low", "close", "volume"]]

    def health_check(self) -> bool:
        try:
            data = self._fetch_json({
                "symbol": "sh000001", "scale": 240, "ma": "no", "datalen": 1,
            })
            return isinstance(data, list) and len(data) > 0
        except Exception:  # noqa: BLE001
            return False
