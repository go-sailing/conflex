"""AKShare 适配器（可选依赖，免费源）。"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from conflex.domain.models import Instrument
from conflex.infra.datasources.base import BaseDataSource, guarded


class AkshareDataSource(BaseDataSource):
    name = "akshare"
    COLUMN_MAP = {
        "日期": "trade_date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "换手率": "turnover",
    }

    def __init__(self):
        super().__init__()

    @guarded
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        try:
            import akshare as ak  # noqa
        except ImportError as exc:  # pragma: no cover
            from conflex.errors import SourceAuthError
            raise SourceAuthError(self.name, "未安装 akshare 包") from exc

        code = symbol.split(".")[0]
        adjust_flag = {"none": "", "qfq": "qfq", "hfq": "hfq"}[adjust]
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust=adjust_flag)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns=self.COLUMN_MAP)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df["symbol"] = symbol
        return df[["symbol", "trade_date", "open", "high", "low", "close",
                    "volume", "amount", "turnover"]]

    def fetch_instruments(self) -> list[Instrument]:
        try:
            import akshare as ak  # noqa
        except ImportError:
            return []
        df = ak.stock_info_a_code_name()
        if df is None or df.empty:
            return []
        out = []
        for _, r in df.iterrows():
            code = str(r["code"])
            symbol = f"{code}.SH" if code.startswith(("6", "9")) else f"{code}.SZ"
            exchange = "SH" if code.startswith(("6", "9")) else "SZ"
            board = ("star" if code.startswith(("688", "689"))
                     else "chinext" if code.startswith(("300", "301")) else "main")
            out.append(Instrument(symbol=symbol, name=r["name"], exchange=exchange,
                                  board=board, list_date=date(2010, 1, 1)))
        return out

    def fetch_calendar(self, start: date, end: date) -> list[date]:
        try:
            import akshare as ak  # noqa
        except ImportError:
            return []
        df = ak.tool_trade_date_hist_sina()
        if df is None or df.empty:
            return []
        dates = pd.to_datetime(df["trade_date"]).dt.date
        return [d for d in dates if start <= d <= end]

    def health_check(self) -> bool:
        try:
            import akshare as ak  # noqa
            ak.tool_trade_date_hist_sina()
            return True
        except Exception:  # noqa: BLE001
            return False
