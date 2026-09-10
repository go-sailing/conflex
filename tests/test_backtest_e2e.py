"""回测端到端黄金样本：可复现、有成交、指标完整、净值连续。"""
from __future__ import annotations

from conflex.domain.backtest.clock import BacktestClock
from conflex.errors import LeakageError
import pandas as pd


def _params():
    return {
        "name": "golden",
        "factors": [{"name": "price_mom_20"}, {"name": "price_rev_20"}],
        "start": "2022-03-01", "end": "2024-12-31",
        "top_n": 5, "rebalance": "M", "initial_cash": 1_000_000,
        "adjust": "none",
    }


def test_backtest_e2e_and_reproducible(container):
    r1 = container.backtest_service.run_sync(_params())
    run1 = container.backtest_service.get_run(r1["run_id"])
    metrics = run1["metrics"]
    assert run1["status"] == "succeeded"
    # 月度调仓两年应有成交
    assert metrics["trade_count"] > 0
    assert metrics["final_equity"] > 0
    for k in ("annual_return", "annual_volatility", "sharpe", "max_drawdown",
              "calmar", "total_return", "total_fee"):
        assert k in metrics
    # 净值序列与交易日对齐
    eq = run1["equity"]
    assert len(eq) > 500
    assert all(row["equity"] > 0 for row in eq)
    # 佣金+印花税为正
    assert metrics["total_fee"] > 0

    # 黄金样本：合成数据确定性 → 同参数结果逐值复现
    r2 = container.backtest_service.run_sync(_params())
    run2 = container.backtest_service.get_run(r2["run_id"])
    assert run2["metrics"] == run1["metrics"]


def test_clock_blocks_future_data():
    clock = BacktestClock(pd.date_range("2024-01-01", periods=3), strict=True)
    assert clock.now == pd.Timestamp("2024-01-01")
    try:
        clock.assert_visible(pd.Timestamp("2024-01-05"))
        assert False, "访问未来数据必须抛 LeakageError"
    except LeakageError:
        pass
    clock.advance()
    clock.assert_visible(pd.Timestamp("2024-01-02"))  # 当前日可见
