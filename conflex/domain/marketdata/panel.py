"""Panel：日期×股票二维不可变面板，因子引擎唯一行情输入（SDD 4.3）。"""
from __future__ import annotations

import pandas as pd

FIELD_NAMES = ("open", "high", "low", "close", "volume", "amount", "turnover")


class PanelData:
    """fields: 字段名 -> DataFrame(index=交易日, columns=symbol)。"""

    def __init__(self, fields: dict[str, pd.DataFrame]):
        if not fields:
            raise ValueError("PanelData 至少需要一个字段")
        self._fields = dict(fields)
        base = next(iter(self._fields.values()))
        self.dates: pd.DatetimeIndex = pd.DatetimeIndex(sorted(base.index.unique()))
        self.symbols: list[str] = list(base.columns)

    def get(self, field: str) -> pd.DataFrame:
        if field not in self._fields:
            raise KeyError(f"面板缺少字段: {field}")
        return self._fields[field]

    def has(self, field: str) -> bool:
        return field in self._fields

    def slice_until(self, dt: pd.Timestamp) -> "PanelData":
        """只返回 index <= dt 的视图 —— 防未来函数的核心取数边界。"""
        ts = pd.Timestamp(dt)
        later = self.dates[self.dates > ts]
        if len(later) == 0:
            return self
        return PanelData({k: v.loc[v.index <= ts] for k, v in self._fields.items()})

    @classmethod
    def from_frames(cls, frames: dict[str, pd.DataFrame]) -> "PanelData":
        frames = {k: v.sort_index() for k, v in frames.items() if v is not None}
        return cls(frames)
