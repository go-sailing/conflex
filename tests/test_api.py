"""Web API 契约：鉴权、数据源、因子、策略、账户、回测、任务轮询。"""
from __future__ import annotations

import time

import pytest

from conflex.entrypoints.webapi.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(container):
    return TestClient(create_app(container))


def _login(client):
    r = client.post("/api/v1/auth/login",
                    json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _wait_job(client, token, job_id, timeout=60):
    for _ in range(timeout * 5):
        r = client.get(f"/api/v1/jobs/{job_id}", headers=_auth(token))
        status = r.json()["status"]
        if status in ("succeeded", "failed", "cancelled"):
            assert status == "succeeded", r.json()
            return r.json()
        time.sleep(0.2)
    raise AssertionError("任务超时")


def test_health_and_auth(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    # 无 token 401
    assert client.get("/api/v1/factors").status_code == 401
    token = _login(client)
    assert client.get("/api/v1/auth/me", headers=_auth(token)).json()["username"] == "admin"
    # 错误密码 401
    assert client.post("/api/v1/auth/login",
                       json={"username": "admin", "password": "x"}).status_code == 401


def test_factors_strategies_and_dashboard(client):
    token = _login(client)
    factors = client.get("/api/v1/factors", headers=_auth(token)).json()
    assert any(f["name"] == "price_mom_20" for f in factors)

    r = client.post("/api/v1/strategies", headers=_auth(token), json={
        "name": "s1", "factors": [{"name": "price_mom_20", "weight": 1.0}],
        "weighting": "equal", "rules": {"top_n": 5}, "rebalance_freq": "M"})
    sid = r.json()["id"]
    assert any(s["id"] == sid for s in
               client.get("/api/v1/strategies", headers=_auth(token)).json())

    dash = client.get("/api/v1/dashboard", headers=_auth(token)).json()
    assert dash["symbol_count"] >= 10
    assert dash["latest_trade_date"] is not None


def test_scores_and_paper_workflow(client):
    token = _login(client)
    r = client.get("/api/v1/scores", headers=_auth(token),
                   params={"factors": "price_mom_20,price_rev_20",
                           "date": "2024-12-31", "top": 5})
    board = r.json()
    assert len(board) == 5 and board[0]["rank"] == 1

    aid = client.post("/api/v1/accounts", headers=_auth(token),
                      json={"name": "demo", "initial_cash": 1_000_000}).json()["id"]
    # 提交买单（信号日次日成交）
    symbol = board[0]["symbol"]
    r = client.post(f"/api/v1/accounts/{aid}/orders", headers=_auth(token),
                    json={"symbol": symbol, "side": "buy", "qty": 1000,
                          "signal_date": "2024-12-30"})
    assert r.status_code == 200
    # 下一交易日撮合 + 结算
    res = client.post(f"/api/v1/accounts/{aid}/market-day", headers=_auth(token),
                      json={"day": "2024-12-31"}).json()
    assert res["filled"] >= 0
    positions = client.get(f"/api/v1/accounts/{aid}/positions",
                           headers=_auth(token)).json()
    assert isinstance(positions, list)


def test_backtest_job_flow(client):
    token = _login(client)
    r = client.post("/api/v1/backtests", headers=_auth(token), json={
        "name": "api-test",
        "factors": [{"name": "price_mom_20"}],
        "start": "2022-06-01", "end": "2024-12-31",
        "top_n": 5, "rebalance": "M", "adjust": "none"})
    job_id = r.json()["job_id"]
    job = _wait_job(client, token, job_id)
    run_id = job["result"]["run_id"]
    report = client.get(f"/api/v1/backtests/{run_id}/report",
                        headers=_auth(token)).json()
    assert report["metrics"]["trade_count"] > 0
    assert len(report["equity"]) > 500
