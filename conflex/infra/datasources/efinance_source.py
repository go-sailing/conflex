"""EFinance 适配器（可选依赖，免费源，东方财富行情）。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from conflex.infra.datasources.base import BaseDataSource, guarded


class EfinanceDataSource(BaseDataSource):
    name = "efinance"
    COLUMN_MAP = {
        "日期": "trade_date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "换手率": "turnover",
    }

    def __init__(self):
        super().__init__()

    @staticmethod
    def _to_ef_code(symbol: str) -> str:
        """东方财富格式: 0.000001（深市）/ 1.600519（沪市）。"""
        parts = symbol.split(".")
        if len(parts) == 2:
            suffix = parts[1]
            code = parts[0]
        else:
            suffix = ""
            code = symbol
        if not suffix:
            if code.startswith(("6", "9")):
                return f"1.{code}"
            return f"0.{code}"
        if suffix.upper() == "SH":
            return f"1.{code}"
        if suffix.upper() == "SZ":
            return f"0.{code}"
        return f"0.{code}"

    @guarded
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        try:
            import efinance as ef  # noqa
        except ImportError as exc:
            from conflex.errors import SourceAuthError
            raise SourceAuthError(self.name, "未安装 efinance 包") from exc

        ef_code = self._to_ef_code(symbol)
        klt = 101  # 日线
        fqt = {"none": 0, "qfq": 1, "hfq": 2}.get(adjust, 0)

        df = ef.stock.get_quote_history(
            ef_code, beg=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"),
            klt=klt, fqt=fqt,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns=self.COLUMN_MAP)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df["symbol"] = symbol
        keep = [c for c in ["symbol", "trade_date", "open", "high", "low", "close",
                            "volume", "amount", "turnover"] if c in df.columns]
        return df[keep]

    def health_check(self) -> bool:
        try:
            import efinance as ef  # noqa
            df = ef.stock.get_quote_history("1.000001", beg="20240101", end="20240102", klt=101)
            return df is not None and not df.empty
        except Exception:  # noqa: BLE001
            return False
