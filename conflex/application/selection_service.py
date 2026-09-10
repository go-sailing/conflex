"""选股服务：因子合成打分与榜单（SDD 6.4）。"""
from __future__ import annotations

import pandas as pd

from conflex.domain.factors.scoring import composite_score, ic_weights, select
from conflex.application.factor_service import FactorService


class SelectionService:
    def __init__(self, factor_service: FactorService, repo):
        self.factors = factor_service
        self.repo = repo

    def score_frame(self, specs: list[dict], panel, weights: dict[str, float] | None = None,
                    weighting: str = "equal") -> pd.DataFrame:
        frames = self.factors.compute_many(specs, panel)
        if weighting == "ic":
            scores = {}
            for name, df in frames.items():
                fwd = None
            # IC 加权：用统一 horizon 的历史 IC 简化计算
            from conflex.domain.factors.analysis import forward_returns, ic_series
            close = panel.get("close")
            icm = {}
            for name, df in frames.items():
                icm[name] = ic_series(df, forward_returns(close, 5)).mean()
            weights = ic_weights(icm)
        return composite_score(frames, weights)

    def board(self, specs: list[dict], panel, on_date: str | pd.Timestamp | None = None,
              top_n: int = 20, weighting: str = "equal") -> pd.DataFrame:
        score = self.score_frame(specs, panel, weighting=weighting)
        if on_date is None:
            row = score.dropna(how="all").iloc[-1]
        else:
            ts = pd.Timestamp(on_date)
            visible = score.loc[score.index <= ts]
            row = visible.iloc[-1]
        ranked = select(row, top_n=top_n)
        # 附加证券名称
        names = {i.symbol: i.name for i in self.repo.load_instruments()}
        ranked["name"] = ranked["symbol"].map(names).fillna("")
        return ranked
