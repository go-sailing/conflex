"""命令行入口（SDD 5）：conflex <command>。

用法：conflex init / data update / factor list / select / paper / backtest / web start
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

import typer

from conflex.container import Container

app = typer.Typer(help="Conflex 多因子量化选股系统", add_completion=False, no_args_is_help=True)
data_app = typer.Typer(help="行情数据")
factor_app = typer.Typer(help="因子研究")
paper_app = typer.Typer(help="模拟交易")
backtest_app = typer.Typer(help="回测")
app.add_typer(data_app, name="data")
app.add_typer(factor_app, name="factor")
app.add_typer(paper_app, name="paper")
app.add_typer(backtest_app, name="backtest")


def _container() -> Container:
    return Container()


def _run_job(c: Container, job_id: int) -> dict:
    """同步等待 Job 完成并打印进度。"""
    q = c.jobs.subscribe(job_id)
    last_stage = ""
    try:
        while True:
            info = c.jobs.get(job_id)
            if info["status"] in ("succeeded", "failed", "cancelled"):
                if info["status"] != "succeeded":
                    typer.secho(f"任务失败：{info.get('error')}", fg=typer.colors.RED)
                    raise typer.Exit(1)
                return info.get("result") or {}
            stage = info.get("stage", "")
            if stage != last_stage:
                typer.echo(f"  [{info['status']}] {stage} {info['progress']*100:.0f}%")
                last_stage = stage
            time.sleep(0.2)
    finally:
        c.jobs.unsubscribe(job_id, q)


@app.command()
def init():
    """初始化本地库并引导证券列表与交易日历。"""
    c = _container()
    try:
        hit = c.market_service.bootstrap()
        typer.secho(f"初始化完成，命中数据源：{hit}", fg=typer.colors.GREEN)
    finally:
        c.close()


@data_app.command("update")
def data_update(symbols: str = typer.Option("", help="逗号分隔，默认全部"),
                start: str = typer.Option(""), end: str = typer.Option("")):
    """增量更新日线（封闭数据永久缓存）。"""
    c = _container()
    try:
        syms = [s.strip() for s in symbols.split(",") if s.strip()] or None
        s = datetime.strptime(start, "%Y-%m-%d").date() if start else None
        e = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
        if not c.market_repo.load_instruments():
            c.market_service.bootstrap()
        job_id = c.market_service.submit_update(syms, s, e)
        result = _run_job(c, job_id)
        typer.secho(f"更新完成：{result.get('ok')}/{result.get('total')}", fg=typer.colors.GREEN)
    finally:
        c.close()


@data_app.command("repair")
def data_repair(symbol: str, start: str, end: str = ""):
    """按区间强制重拉单只股票。"""
    c = _container()
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end or date.today().isoformat(), "%Y-%m-%d").date()
        job_id = c.market_service.submit_repair(symbol, s, e)
        _run_job(c, job_id)
        typer.secho("修复完成", fg=typer.colors.GREEN)
    finally:
        c.close()


@data_app.command("coverage")
def data_coverage():
    """查看本地缓存覆盖情况。"""
    c = _container()
    try:
        for row in c.market_service.coverage():
            typer.echo(f"{row['symbol']:12} {row['start_date']} ~ {row['end_date']} "
                       f"final={row['is_final']} src={row['source']}")
    finally:
        c.close()


@factor_app.command("list")
def factor_list():
    """列出全部已注册因子。"""
    c = _container()
    try:
        for f in c.factor_service.list_factors():
            typer.echo(f"{f['name']:22} [{f['category']:6}] {f['description']}")
    finally:
        c.close()


@factor_app.command("analyze")
def factor_analyze(name: str, start: str, end: str = "", horizon: int = 5, groups: int = 10):
    """计算因子 IC 与分层收益。"""
    c = _container()
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end or date.today().isoformat(), "%Y-%m-%d").date()
        symbols = c.market_service.listed_symbols()
        panel = c.factor_service.load_panel(symbols, s, e)
        result = c.factor_service.analyze(name, panel, horizon, groups)
        typer.echo(json.dumps({"summary": result["summary"],
                               "layered_mean": result["layered_mean"]},
                              ensure_ascii=False, indent=2))
    finally:
        c.close()


@app.command("select")
def select_cmd(factors: str = typer.Option(..., help="逗号分隔因子名"),
               top: int = 20, start: str = "", end: str = "",
               weighting: str = "equal"):
    """生成选股榜单。"""
    c = _container()
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date() if start else None
        e = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
        symbols = c.market_service.listed_symbols()
        panel = c.factor_service.load_panel(symbols, s, e)
        specs = [{"name": n} for n in factors.split(",")]
        board = c.selection_service.board(specs, panel, top_n=top, weighting=weighting)
        typer.echo(board.to_string(index=False))
    finally:
        c.close()


@paper_app.command("create")
def paper_create(name: str, cash: float = 1_000_000):
    """创建模拟账户。"""
    c = _container()
    try:
        typer.echo(f"account_id={c.paper_service.create_account(name, cash)}")
    finally:
        c.close()


@paper_app.command("positions")
def paper_positions(account_id: int):
    c = _container()
    try:
        positions = c.paper_service.positions(account_id)
        if not positions:
            typer.echo("（空仓）")
        for p in positions:
            typer.echo(p)
    finally:
        c.close()


@paper_app.command("day")
def paper_day(account_id: int, day: str = ""):
    """执行某交易日：T+1 撮合待报订单并收盘结算。"""
    c = _container()
    try:
        d = datetime.strptime(day or date.today().isoformat(), "%Y-%m-%d").date()
        typer.echo(c.paper_service.run_market_day(account_id, d))
    finally:
        c.close()


@backtest_app.command("run")
def backtest_run(factors: str = typer.Option(...), start: str = typer.Option(...),
                 end: str = typer.Option(...), top: int = 20,
                 rebalance: str = "M", cash: float = 1_000_000,
                 benchmark: str = "", adjust: str = "qfq"):
    """运行回测。"""
    c = _container()
    try:
        params = {"name": "cli-backtest", "factors": [{"name": n} for n in factors.split(",")],
                  "start": start, "end": end, "top_n": top, "rebalance": rebalance,
                  "initial_cash": cash, "benchmark": benchmark, "adjust": adjust}
        job_id = c.backtest_service.submit(params)
        result = _run_job(c, job_id)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        c.close()


@app.command("web")
def web_cmd(host: str = "127.0.0.1", port: int = 8899):
    """启动 Web 管理后台。"""
    import uvicorn

    from conflex.entrypoints.webapi.app import create_app
    from conflex.config import load_settings

    settings = load_settings()
    settings.web_host, settings.web_port = host, port
    container = Container(settings)
    fastapi_app = create_app(container)
    typer.secho(f"Conflex Web: http://{host}:{port}", fg=typer.colors.GREEN)
    uvicorn.run(fastapi_app, host=host, port=port)


def main():
    app()


if __name__ == "__main__":
    main()
