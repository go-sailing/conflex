"""日线数据质量校验纯函数（SDD 5.5）。"""
from __future__ import annotations

import pandas as pd

BAR_COLUMNS = [
    "symbol", "trade_date", "open", "high", "low", "close",
    "volume", "amount", "turnover", "pre_close", "suspended",
]

REQUIRED = ["trade_date", "open", "high", "low", "close", "volume"]


def validate_daily(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。error 级数据应进入隔离区，不写入正式缓存。"""
    errors: list[str] = []
    warnings: list[str] = []
    if df is None or df.empty:
        return ["数据为空"], warnings

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        errors.append(f"缺少关键字段: {missing}")
        return errors, warnings

    for col in ("open", "high", "low", "close"):
        bad = df[(df[col].notna()) & (df[col] <= 0)]
        if not bad.empty:
            errors.append(f"{col} 存在非正价格 {len(bad)} 行")

    ohlc_bad = df[
        (df["high"] < df["low"])
        | (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
    ]
    if not ohlc_bad.empty:
        errors.append(f"OHLC 关系非法 {len(ohlc_bad)} 行")

    dup = df["trade_date"].duplicated()
    if dup.any():
        errors.append(f"交易日重复 {int(dup.sum())} 行")

    if "pre_close" in df.columns:
        jump = df[df["pre_close"].notna() & (df["pre_close"] > 0)]
        jump = jump[(jump["close"] / jump["pre_close"] - 1).abs() > 0.22]
        if not jump.empty:
            warnings.append(f"疑似异常跳变(>22%) {len(jump)} 行")

    vol_bad = df[(df["volume"] < 0)]
    if not vol_bad.empty:
        errors.append("成交量为负")

    return errors, warnings
