"""截面预处理流水线纯函数（SDD 6.3）。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _cross_section(df: pd.DataFrame) -> pd.DataFrame:
    return df


def drop_low_coverage(min_count: int):
    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        # 小股票池下阈值自适应：至少要求半数覆盖，且不少于 5 只
        threshold = min(min_count, max(5, (df.shape[1] + 1) // 2))
        keep = (df.notna().sum(axis=1) >= threshold).to_numpy()
        cond = np.repeat(keep[:, None], df.shape[1], axis=1)
        return df.where(cond)
    return _fn


def fillna_median(df: pd.DataFrame) -> pd.DataFrame:
    med = df.median(axis=1)
    return df.apply(lambda col: col.fillna(med))


def winsorize_mad(n: float = 3.0):
    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        med = df.median(axis=1)
        mad = (df.sub(med, axis=0)).abs().median(axis=1).replace(0, np.nan)
        bound = n * 1.4826 * mad
        lower = (med - bound).to_numpy()[:, None]
        upper = (med + bound).to_numpy()[:, None]
        return pd.DataFrame(np.clip(df.to_numpy(), lower, upper),
                            index=df.index, columns=df.columns)
    return _fn


def winsorize_sigma(n: float = 3.0):
    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        mean = df.mean(axis=1)
        std = df.std(axis=1).replace(0, np.nan)
        lower = (mean - n * std).to_numpy()[:, None]
        upper = (mean + n * std).to_numpy()[:, None]
        return pd.DataFrame(np.clip(df.to_numpy(), lower, upper),
                            index=df.index, columns=df.columns)
    return _fn


def zscore(df: pd.DataFrame) -> pd.DataFrame:
    mean = df.mean(axis=1)
    std = df.std(axis=1).replace(0, np.nan)
    return df.sub(mean, axis=0).div(std, axis=0)


def neutralize(industry: pd.DataFrame | None = None, log_mv: pd.DataFrame | None = None):
    """对行业哑变量/对数市值回归取残差（按截面 OLS）。"""

    def _fn(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for dt in df.index:
            y = df.loc[dt]
            valid = y.notna()
            x_cols = []
            if industry is not None and dt in industry.index:
                d = pd.get_dummies(industry.loc[dt].reindex(y.index), dummy_na=False)
                x_cols.append(d)
            if log_mv is not None and dt in log_mv.index:
                x_cols.append(log_mv.loc[dt].reindex(y.index).to_frame("log_mv"))
            if not x_cols or valid.sum() < 3:
                continue
            X = pd.concat(x_cols, axis=1).astype(float)
            X = X.loc[valid].fillna(0.0)
            yv = y[valid].astype(float)
            X.insert(0, "_const", 1.0)
            try:
                beta, *_ = np.linalg.lstsq(X.to_numpy(), yv.to_numpy(), rcond=None)
                resid = yv - X.to_numpy() @ beta
                out.loc[dt, resid.index] = resid
            except np.linalg.LinAlgError:
                continue
        return out

    return _fn


DEFAULT_PIPELINE = [
    drop_low_coverage(min_count=50),
    fillna_median,
    winsorize_mad(n=3),
    zscore,
]


def run_pipeline(df: pd.DataFrame, steps=None) -> pd.DataFrame:
    for step in (steps or DEFAULT_PIPELINE):
        df = step(df)
    return df
