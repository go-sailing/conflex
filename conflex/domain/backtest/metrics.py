"""绩效指标纯函数（SDD 8.4），黄金样本逐值校验。"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 244


def equity_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().fillna(0.0)


def annualized_return(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    years = max(len(equity) / TRADING_DAYS, 1e-9)
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def annualized_volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(returns) > 2 else 0.0


def max_drawdown(equity: pd.Series) -> tuple[float, int]:
    """返回 (最大回撤(正值), 回撤持续交易日数)。"""
    if equity.empty:
        return 0.0, 0
    peak = equity.cummax()
    dd = 1 - equity / peak
    mdd = float(dd.max())
    # 持续期：峰值到最低点之间的天数（近似）
    end = int(dd.values.argmax())
    start = int(equity.iloc[: end + 1].values.argmax())
    return mdd, end - start


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    if len(returns) < 3:
        return 0.0
    excess = returns - rf / TRADING_DAYS
    std = excess.std(ddof=1)
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS)) if std > 0 else 0.0


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    if len(returns) < 3:
        return 0.0
    excess = returns - rf / TRADING_DAYS
    downside = excess[excess < 0].std(ddof=1)
    return float(excess.mean() / downside * np.sqrt(TRADING_DAYS)) if downside and downside > 0 else 0.0


def calmar(ann_return: float, mdd: float) -> float:
    return float(ann_return / mdd) if mdd > 0 else 0.0


def information_ratio(returns: pd.Series, bench_returns: pd.Series) -> float:
    idx = returns.index.intersection(bench_returns.index)
    if len(idx) < 3:
        return 0.0
    active = returns.loc[idx] - bench_returns.loc[idx]
    std = active.std(ddof=1)
    return float(active.mean() / std * np.sqrt(TRADING_DAYS)) if std > 0 else 0.0


def monthly_returns(equity: pd.Series) -> pd.DataFrame:
    if equity.empty:
        return pd.DataFrame()
    monthly = equity.resample("ME").last()
    mr = monthly.pct_change().dropna()
    table = pd.DataFrame({"year": mr.index.year, "month": mr.index.month, "ret": mr.values})
    return table.pivot_table(index="year", columns="month", values="ret")


def compute_metrics(
    equity: pd.Series,
    benchmark: pd.Series | None = None,
    rf: float = 0.02,
) -> dict:
    rets = equity_returns(equity)
    ann = annualized_return(equity)
    mdd, mdd_days = max_drawdown(equity)
    out = {
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) else 0.0,
        "annual_return": ann,
        "annual_volatility": annualized_volatility(rets),
        "sharpe": sharpe(rets, rf),
        "sortino": sortino(rets, rf),
        "max_drawdown": mdd,
        "max_drawdown_days": mdd_days,
        "calmar": calmar(ann, mdd),
    }
    if benchmark is not None and not benchmark.empty:
        b_rets = equity_returns(benchmark.reindex(equity.index).ffill())
        out["benchmark_return"] = annualized_return(benchmark.reindex(equity.index).ffill())
        out["information_ratio"] = information_ratio(rets, b_rets)
        # 相对基准的超额净值曲线
    return out
