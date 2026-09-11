"""BaoStock 适配器（可选依赖，免费源，无需注册）。"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import date, timedelta

import pandas as pd

from conflex.domain.models import Instrument
from conflex.infra.datasources.base import BaseDataSource, guarded

_LOGIN_TIMEOUT = 10  # seconds


class BaostockDataSource(BaseDataSource):
    name = "baostock"
    COLUMN_MAP = {
        "date": "trade_date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "amount": "amount",
        "turn": "turnover",
        "preclose": "pre_close",
        "isST": "suspended",
    }

    def __init__(self):
        super().__init__()
        self._logged_in = False

    def _ensure_login(self):
        if self._logged_in:
            return
        try:
            import baostock as bs  # noqa
        except ImportError as exc:
            from conflex.errors import SourceAuthError
            raise SourceAuthError(self.name, "未安装 baostock 包") from exc

        def _do_login():
            return bs.login()

        with ThreadPoolExecutor(1) as pool:
            try:
                lg = pool.submit(_do_login).result(timeout=_LOGIN_TIMEOUT)
            except FuturesTimeout:
                from conflex.errors import SourceNetworkError
                raise SourceNetworkError(self.name, f"baostock 登录超时({_LOGIN_TIMEOUT}s)")
            except socket.timeout:
                from conflex.errors import SourceNetworkError
                raise SourceNetworkError(self.name, "baostock 连接超时")
            except Exception as exc:
                from conflex.errors import SourceNetworkError
                raise SourceNetworkError(self.name, f"baostock 登录异常: {exc}") from exc

        if lg.error_code != "0":
            from conflex.errors import SourceAuthError
            raise SourceAuthError(self.name, f"baostock 登录失败: {lg.error_msg}")
        self._logged_in = True

    @staticmethod
    def _to_bs_code(symbol: str) -> str:
        """sz.000001 / sh.600519 格式。"""
        parts = symbol.split(".")
        if len(parts) == 2:
            return f"{parts[1]}.{parts[0].lower()}"
        code = symbol
        if code.startswith(("6", "9")):
            return f"{code}.sh"
        return f"{code}.sz"

    @staticmethod
    def _from_bs_code(bs_code: str) -> str:
        """sh.600519 -> 600519.SH 格式。"""
        parts = bs_code.split(".")
        if len(parts) == 2:
            return f"{parts[1]}.{parts[0].upper()}"
        return bs_code

    @guarded
    def _raw_daily(self, symbol: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        import baostock as bs  # noqa

        self._ensure_login()
        bs_code = self._to_bs_code(symbol)
        adjust_map = {"none": "", "qfq": "2", "hfq": "1"}
        adjustflag = adjust_map.get(adjust, "")

        fields = "date,open,high,low,close,volume,amount,turn,preclose,isST"
        rs = bs.query_history_k_data_plus(
            bs_code, fields,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            frequency="d", adjustflag=adjustflag,
        )
        if rs.error_code != "0":
            return pd.DataFrame()

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)
        df = df.replace("", pd.NA)
        df["trade_date"] = pd.to_datetime(df["date"])
        df["symbol"] = symbol
        for col in ("open", "high", "low", "close", "volume", "amount", "turn", "preclose"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["isST"] = df["isST"].map({"1": True, "0": False}).fillna(False)
        df = df.rename(columns={"turn": "turnover", "preclose": "pre_close", "isST": "suspended"})
        return df[["symbol", "trade_date", "open", "high", "low", "close",
                    "volume", "amount", "turnover", "pre_close", "suspended"]]

    def fetch_instruments(self) -> list[Instrument]:
        try:
            import baostock as bs  # noqa
        except ImportError:
            return []
        self._ensure_login()
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            return []
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return []
        df = pd.DataFrame(rows, columns=rs.fields)
        out = []
        for _, r in df.iterrows():
            status = r.get("status", "1")
            if status != "1":
                continue
            bs_code = r["code"]
            symbol = self._from_bs_code(bs_code)
            code = bs_code.split(".")[1]
            exchange = "SH" if bs_code.startswith("sh") else "SZ"
            board = ("star" if code.startswith(("688", "689"))
                     else "chinext" if code.startswith(("300", "301")) else "main")
            list_date_str = r.get("ipoDate", "")
            list_date = date.fromisoformat(list_date_str) if list_date_str else date(2010, 1, 1)
            out.append(Instrument(symbol=symbol, name=r.get("code_name", ""),
                                  exchange=exchange, board=board, list_date=list_date))
        return out

    @guarded
    def fetch_index_members(self, index_code: str) -> list[tuple[str, str]]:
        """baostock 仅支持沪深300（000300）与中证500（000905）。"""
        try:
            import baostock as bs  # noqa
        except ImportError:
            return []
        if index_code == "000300":
            query = bs.query_hs300_stocks
        elif index_code == "000905":
            query = bs.query_zz500_stocks
        else:
            return []
        self._ensure_login()
        rs = query()
        if rs.error_code != "0":
            return []
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return []
        df = pd.DataFrame(rows, columns=rs.fields)
        out: list[tuple[str, str]] = []
        for _, r in df.iterrows():
            out.append((self._from_bs_code(r["code"]), r.get("code_name", "")))
        return out

    def fetch_calendar(self, start: date, end: date) -> list[date]:
        try:
            import baostock as bs  # noqa
        except ImportError:
            return []
        self._ensure_login()
        rs = bs.query_trade_dates(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        if rs.error_code != "0":
            return []
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        dates = []
        for r in rows:
            if r[1] == "1":  # is_trading_day
                dates.append(date.fromisoformat(r[0]))
        return dates

    def health_check(self) -> bool:
        try:
            import baostock as bs  # noqa
            self._ensure_login()
            rs = bs.query_history_k_data_plus(
                "sh.000001", "date",
                start_date=date.today().strftime("%Y-%m-%d"),
                end_date=date.today().strftime("%Y-%m-%d"),
                frequency="d",
            )
            return rs.error_code == "0"
        except Exception:  # noqa: BLE001
            return False
