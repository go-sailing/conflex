"""Tushare Pro 适配器（可选依赖，token 从环境变量注入）。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from conflex.domain.models import Instrument
from conflex.errors import SourceAuthError
from conflex.infra.datasources.base import BaseDataSource, guarded


class TushareDataSource(BaseDataSource):
    name = "tushare"
    COLUMN_MAP = {
        "trade_date": "trade_date", "vol": "volume", "pct_chg": "pct_chg",
    }

    def __init__(self, token: str = ""):
        super().__init__()
        self.token = token
        self._pro = None

    def _client(self):
        if self._pro is None:
            try:
                import tushare as ts  # noqa
            except ImportError as exc:  # pragma: no cover
                raise SourceAuthError(self.name, "未安装 tushare 包") from exc
            if not self.token:
                raise SourceAuthError(self.name, "缺少 TUSHARE_TOKEN")
            ts.set_token(self.token)
            self._pro = ts.pro_api()
        return self._pro

    @staticmethod
    def _to_ts_code(symbol: str) -> str:
        return symbol.replace(".SH", ".SH").replace(".SZ", ".SZ")

    @guarded
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        import tushare as ts  # noqa

        ts_code = self._to_ts_code(symbol)
        if adjust == "none":
            pro = self._client()
            df = pro.daily(
                ts_code=ts_code,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"))
            df = df.rename(columns={"vol": "volume"})
        else:
            adj = "qfq" if adjust == "qfq" else "hfq"
            df = ts.pro_bar(ts_code=ts_code, adj=adj,
                            start_date=start.strftime("%Y%m%d"),
                            end_date=end.strftime("%Y%m%d"))
        if df is None or df.empty:
            return pd.DataFrame()
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df["symbol"] = symbol
        return df

    def fetch_instruments(self) -> list[Instrument]:  # pragma: no cover - 需联网
        pro = self._client()
        df = pro.stock_basic(exchange="", list_status="L",
                             fields="ts_code,name,list_date,market")
        out = []
        for _, r in df.iterrows():
            ts_code = r["ts_code"]
            symbol = ts_code
            code = ts_code.split(".")[0]
            board = ("star" if code.startswith(("688", "689"))
                     else "chinext" if code.startswith(("300", "301")) else "main")
            out.append(Instrument(symbol, r["name"], ts_code[-2:], board=board,
                                  list_date=date.fromisoformat(str(r["list_date"]))))
        return out

    def health_check(self) -> bool:
        try:
            self._client().trade_cal(exchange="SSE", limit=1)
            return True
        except Exception:  # noqa: BLE001
            return False
