"""因子引擎：计算、预处理、IC 分析、合成打分。"""
from __future__ import annotations

from tests.conftest import END, START


def test_factor_registry_builtins(container):
    names = {f["name"] for f in container.factor_service.list_factors()}
    assert {"price_mom_20", "price_rev_20", "risk_vol_60", "tech_rsi_14"} <= names


def test_compute_factor_shape_and_preprocess(container):
    symbols = container.market_service.listed_symbols()
    panel = container.factor_service.load_panel(symbols, START, END)
    value = container.factor_service.compute("price_mom_20", panel)
    # 截面标准化：成熟期行均值≈0、标准差≈1
    mature = value.dropna(how="all").iloc[-1].dropna()
    assert len(mature) >= 5
    assert abs(mature.mean()) < 1e-8
    assert abs(mature.std(ddof=1) - 1.0) < 1e-6


def test_factor_analysis_ic(container):
    symbols = container.market_service.listed_symbols()
    panel = container.factor_service.load_panel(symbols, START, END)
    result = container.factor_service.analyze("price_rev_20", panel, horizon=5, groups=5)
    summary = result["summary"]
    assert summary["count"] > 0
    assert set(summary) == {"ic_mean", "ic_std", "icir", "win_rate", "count"}
    assert len(result["layered_mean"]) == 5


def test_selection_board(container):
    symbols = container.market_service.listed_symbols()
    panel = container.factor_service.load_panel(symbols, START, END)
    board = container.selection_service.board(
        [{"name": "price_mom_20"}, {"name": "risk_vol_60"}], panel, top_n=5)
    assert len(board) == 5
    assert list(board["rank"]) == [1, 2, 3, 4, 5]
    assert board["score"].is_monotonic_decreasing
