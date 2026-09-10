"""模拟账户、订单、调仓路由。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from conflex.entrypoints.webapi.deps import get_container, require_admin

router = APIRouter(tags=["paper"])


class AccountIn(BaseModel):
    name: str
    initial_cash: float = 1_000_000


@router.get("/accounts")
def list_accounts(container=Depends(get_container), user=Depends(require_admin)):
    return container.paper_service.list_accounts()


@router.post("/accounts")
def create_account(body: AccountIn, container=Depends(get_container),
                   user=Depends(require_admin)):
    aid = container.paper_service.create_account(body.name, body.initial_cash)
    return {"id": aid}


@router.get("/accounts/{aid}/positions")
def positions(aid: int, container=Depends(get_container), user=Depends(require_admin)):
    return container.paper_service.positions(aid)


@router.get("/accounts/{aid}/orders")
def orders(aid: int, status: str | None = None, container=Depends(get_container),
           user=Depends(require_admin)):
    return container.paper_service.orders(aid, status)


@router.get("/accounts/{aid}/trades")
def trades(aid: int, container=Depends(get_container), user=Depends(require_admin)):
    return container.paper_service.trades(aid)


@router.get("/accounts/{aid}/equity")
def equity(aid: int, container=Depends(get_container), user=Depends(require_admin)):
    return container.paper_service.equity_curve(aid)


class OrderIn(BaseModel):
    symbol: str
    side: str            # buy / sell
    qty: int
    signal_date: str | None = None


@router.post("/accounts/{aid}/orders")
def place_order(aid: int, body: OrderIn, container=Depends(get_container),
                user=Depends(require_admin)):
    sd = datetime.strptime(body.signal_date, "%Y-%m-%d").date() if body.signal_date else None
    return container.paper_service.submit_order(
        aid, body.symbol, body.side, body.qty, signal_date=sd)


@router.delete("/orders/{oid}")
def cancel_order(oid: int, account_id: int, container=Depends(get_container),
                 user=Depends(require_admin)):
    return container.paper_service.cancel_order(account_id, oid)


class RebalanceIn(BaseModel):
    weights: dict[str, float]
    on: str | None = None
    commit: bool = False


@router.post("/accounts/{aid}/rebalance")
def rebalance(aid: int, body: RebalanceIn, container=Depends(get_container),
              user=Depends(require_admin)):
    on = datetime.strptime(body.on, "%Y-%m-%d").date() if body.on else None
    if body.commit:
        return container.paper_service.rebalance_commit(aid, body.weights, on)
    return container.paper_service.rebalance_preview(aid, body.weights, on)


class MarketDayIn(BaseModel):
    day: str | None = None


@router.post("/accounts/{aid}/market-day")
def market_day(aid: int, body: MarketDayIn, container=Depends(get_container),
               user=Depends(require_admin)):
    day = datetime.strptime(body.day or date.today().isoformat(), "%Y-%m-%d").date()
    return container.paper_service.run_market_day(aid, day)
