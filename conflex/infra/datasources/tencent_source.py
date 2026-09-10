"""腾讯财经适配器（免费源，HTTP API，无需额外依赖）。"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, timedelta
from urllib.parse import urlencode

import pandas as pd

from conflex.infra.datasources.base import BaseDataSource, guarded


class TencentDataSource(BaseDataSource):
    name = "tencent"
    COLUMN_MAP = {
        "date": "trade_date", "volume": "volume",
    }

    _BASE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self):
        super().__init__()

    @staticmethod
    def _to_qq_code(symbol: str) -> str:
        """sh600519 / sz000001 格式。"""
        parts = symbol.split(".")
        if len(parts) == 2:
            code, market = parts
            return f"{market.lower()}{code}"
        code = symbol
        if code.startswith(("6", "9")):
            return f"sh{code}"
        return f"sz{code}"

    def _fetch_json(self, params: dict) -> dict:
        url = f"{self._BASE_URL}?{urlencode({'param': params['param']})}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    @guarded
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        qq_code = self._to_qq_code(symbol)
        days_span = (end - start).days + 30
        count = min(max(days_span, 640), 640)

        fqt_map = {"none": "", "qfq": "qfq", "hfq": "hfq"}
        fqt = fqt_map.get(adjust, "")

        end_str = end.strftime("%Y-%m-%d")
        param = f"{qq_code},day,,{end_str},{count},{fqt}"
        data = self._fetch_json({"param": param})

        stock_data = data.get("data", {}).get(qq_code, {})
        day_data = stock_data.get("day") or stock_data.get("qfqday") or stock_data.get("hfqday") or []

        if not day_data:
            return pd.DataFrame()

        # [date, open, close, high, low, volume] — 有时多一列
        df = pd.DataFrame(day_data)
        df = df.iloc[:, :6]
        df.columns = ["trade_date", "open", "close", "high", "low", "volume"]
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["symbol"] = symbol
        df = df[(df["trade_date"].dt.date >= start) & (df["trade_date"].dt.date <= end)]
        return df[["symbol", "trade_date", "open", "high", "low", "close", "volume"]]

    def health_check(self) -> bool:
        try:
            data = self._fetch_json({"param": "sh000001,day,,,1,"})
            return bool(data.get("data"))
        except Exception:  # noqa: BLE001
            return False
