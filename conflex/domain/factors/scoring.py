"""因子合成、打分与选股过滤（SDD 6.4）。"""
from __future__ import annotations

import pandas as pd


def composite_score(
    frames: dict[str, pd.DataFrame],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """加权合成。frames 中各因子应已完成截面标准化。"""
    if not frames:
        raise ValueError("至少需要一个因子")
    weights = weights or {name: 1.0 / len(frames) for name in frames}
    total = sum(weights.get(n, 0.0) for n in frames)
    if total <= 0:
        raise ValueError("因子权重之和必须为正")

    score = None
    for name, df in frames.items():
        w = weights.get(name, 0.0) / total
        part = df.fillna(0.0) * w
        score = part if score is None else score.add(part, fill_value=0.0)
    return score


def select(
    score: pd.Series,
    top_n: int | None = None,
    pct: float | None = None,
    min_score: float | None = None,
) -> pd.DataFrame:
    """按综合得分排序输出榜单。score：index=symbol 的某一截面 Series。

    停牌/ST/次新等不可交易过滤由调用方在传入前剔除。
    """
    s = score.dropna().sort_values(ascending=False)
    if min_score is not None:
        s = s[s >= min_score]
    if top_n is not None:
        s = s.head(top_n)
    elif pct is not None:
        s = s.head(max(1, int(len(s) * pct)))

    df = pd.DataFrame({"symbol": s.index, "score": s.values})
    df["rank"] = range(1, len(df) + 1)
    n = max(len(s), 1)
    df["quantile"] = ((df["rank"] - 1) * 10 // n) + 1
    return df.reset_index(drop=True)


def ic_weights(ic_means: dict[str, float]) -> dict[str, float]:
    """以历史 IC 均值绝对值作为合成权重（IC 加权简化实现）。"""
    pos = {k: max(v, 0.0) for k, v in ic_means.items()}
    total = sum(pos.values())
    if total <= 0:
        return {k: 1.0 / len(pos) for k in pos}
    return {k: v / total for k, v in pos.items()}
