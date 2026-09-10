"""因子有效性分析：IC / 分层 / 相关性（SDD 6.5，纯函数）。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_returns(close: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """t 日因子对应未来 horizon 日收益率（严格右对齐，不含未来函数）。"""
    return close.shift(-horizon) / close - 1.0


def _corr(a: pd.Series, b: pd.Series, method: str) -> float:
    """pearson / spearman，spearman 用排名后 pearson 实现（免 scipy 依赖）。"""
    if method == "spearman":
        a = a.rank()
        b = b.rank()
    return a.corr(b, method="pearson")


def ic_series(
    factor: pd.DataFrame,
    fwd_ret: pd.DataFrame,
    method: str = "spearman",
) -> pd.Series:
    """逐日截面 IC 序列。"""
    aligned_f, aligned_r = factor.align(fwd_ret, join="inner")
    vals = []
    for dt in aligned_f.index:
        df = pd.concat([aligned_f.loc[dt], aligned_r.loc[dt]],
                       axis=1, keys=["f", "r"]).dropna()
        if len(df) < 5:
            vals.append(np.nan)
            continue
        vals.append(_corr(df["f"], df["r"], method))
    return pd.Series(vals, index=aligned_f.index, name="ic")


def ic_summary(ic: pd.Series) -> dict:
    ic = ic.dropna()
    if ic.empty:
        return {"ic_mean": None, "ic_std": None, "icir": None, "win_rate": None, "count": 0}
    std = ic.std(ddof=1)
    return {
        "ic_mean": float(ic.mean()),
        "ic_std": float(std),
        "icir": float(ic.mean() / std) if std and std > 0 else None,
        "win_rate": float((ic > 0).mean()),
        "count": int(len(ic)),
    }


def layered_returns(
    factor: pd.DataFrame, fwd_ret: pd.DataFrame, groups: int = 10
) -> pd.DataFrame:
    """每个交易日按因子分 groups 组，返回各组平均未来收益（按日期均值聚合）。"""
    aligned_f, aligned_r = factor.align(fwd_ret, join="inner")
    rows = []
    for dt in aligned_f.index:
        df = pd.concat([aligned_f.loc[dt], aligned_r.loc[dt]], keys=["f", "r"], axis=1).dropna()
        if len(df) < groups:
            continue
        ranked = df["f"].rank(method="first")
        grp = pd.qcut(ranked, groups, labels=False) + 1
        rows.append(df["r"].groupby(grp).mean())
    if not rows:
        return pd.DataFrame()
    layered = pd.DataFrame(rows)
    return layered


def factor_correlation(frames: dict[str, pd.DataFrame], method: str = "spearman") -> pd.DataFrame:
    """因子值展平后的两两相关性矩阵。"""
    flat = {}
    for name, df in frames.items():
        flat[name] = df.values[~np.isnan(df.values)]
    # 长度可能因窗口不同，取共同样本
    series = [pd.Series(v) for v in flat.values()]
    min_len = min(len(s) for s in series)
    data = {name: s.iloc[:min_len].reset_index(drop=True) for name, s in zip(flat, series)}
    if method == "spearman":
        data = {k: v.rank() for k, v in data.items()}
    return pd.DataFrame(data).corr(method="pearson")
