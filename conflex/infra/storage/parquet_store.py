"""日线 Parquet 分区存储：按 symbol/year 分区，upsert 幂等（SDD 5.4）。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from conflex.domain.marketdata.quality import BAR_COLUMNS
from conflex.infra.storage.paths import adjust_file, bar_file


class ParquetStore:
    def __init__(self, root):
        self.root = root

    # ---- 日线 ----
    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        for col in ("open", "high", "low", "close", "volume", "amount",
                    "turnover", "pre_close"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "suspended" not in df.columns:
            df["suspended"] = False
        df["suspended"] = df["suspended"].fillna(False).astype(bool)
        for col in BAR_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[BAR_COLUMNS].sort_values("trade_date")

    def read(self, symbol: str, start=None, end=None) -> pd.DataFrame:
        start = pd.Timestamp(start).date() if start else None
        end = pd.Timestamp(end).date() if end else None
        d = self.root / "daily" / symbol
        frames = []
        if d.exists():
            for f in sorted(d.glob("*.parquet")):
                if start and int(f.stem) < start.year:
                    continue
                if end and int(f.stem) > end.year:
                    continue
                frames.append(pq.read_table(f).to_pandas())
        if not frames:
            return pd.DataFrame(columns=BAR_COLUMNS)
        df = pd.concat(frames, ignore_index=True).drop_duplicates("trade_date", keep="last")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values("trade_date")
        if start:
            df = df[df["trade_date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["trade_date"] <= pd.Timestamp(end)]
        return df.reset_index(drop=True)

    def upsert(self, symbol: str, df: pd.DataFrame) -> None:
        """按年合并去重（保留最新），保证重复拉取幂等。"""
        df = self._normalize(df)
        if df.empty:
            return
        df["_year"] = df["trade_date"].dt.year
        for year, chunk in df.groupby("_year"):
            chunk = chunk.drop(columns="_year")
            path = bar_file(self.root, symbol, int(year))
            if path.exists():
                old = pq.read_table(path).to_pandas()
                old["trade_date"] = pd.to_datetime(old["trade_date"])
                chunk = (
                    pd.concat([old, chunk], ignore_index=True)
                    .drop_duplicates("trade_date", keep="last")
                    .sort_values("trade_date")
                )
            pq.write_table(pa.Table.from_pandas(chunk, preserve_index=False), path,
                           compression="snappy")

    # ---- 复权因子 ----
    def read_adjust(self, symbol: str) -> pd.DataFrame:
        path = adjust_file(self.root, symbol)
        if not path.exists():
            return pd.DataFrame(columns=["trade_date", "factor"])
        df = pq.read_table(path).to_pandas()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df.sort_values("trade_date")

    def upsert_adjust(self, symbol: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        path = adjust_file(self.root, symbol)
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        if path.exists():
            old = pq.read_table(path).to_pandas()
            old["trade_date"] = pd.to_datetime(old["trade_date"])
            df = pd.concat([old, df], ignore_index=True).drop_duplicates(
                "trade_date", keep="last"
            ).sort_values("trade_date")
        pq.write_table(pa.Table.from_pandas(df[["trade_date", "factor"]],
                                           preserve_index=False), path, compression="snappy")

    def latest_bar(self, symbol: str) -> dict | None:
        """读取最新一根日线（只打开年份最大的分区文件，取末行）。"""
        d = self.root / "daily" / symbol
        if not d.exists():
            return None
        files = sorted(d.glob("*.parquet"))
        if not files:
            return None
        df = pq.read_table(files[-1]).to_pandas()
        if df.empty:
            return None
        df = df.sort_values("trade_date")
        row = df.iloc[-1]
        pre_close = row.get("pre_close")
        if pd.isna(pre_close) and len(df) >= 2:
            pre_close = df.iloc[-2]["close"]  # 当日增量行缺失 pre_close 时用上一根收盘兜底
        change_pct = None
        if pd.notna(pre_close) and float(pre_close) > 0 and pd.notna(row.get("close")):
            change_pct = round((float(row["close"]) / float(pre_close) - 1) * 100, 2)
        return {
            "trade_date": pd.Timestamp(row["trade_date"]).strftime("%Y-%m-%d"),
            "close": (None if pd.isna(row.get("close")) else round(float(row["close"]), 4)),
            "pre_close": (None if pd.isna(pre_close) else round(float(pre_close), 4)),
            "change_pct": change_pct,
            "volume": (None if pd.isna(row.get("volume")) else float(row["volume"])),
            "amount": (None if pd.isna(row.get("amount")) else round(float(row["amount"]), 2)),
            "turnover": (None if pd.isna(row.get("turnover")) else round(float(row["turnover"]), 3)),
        }

    def symbols(self) -> list[str]:
        d = self.root / "daily"
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    def storage_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.rglob("*.parquet"))
