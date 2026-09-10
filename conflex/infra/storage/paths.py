"""数据目录布局（SDD 3.1）。"""
from __future__ import annotations

from pathlib import Path

from conflex.domain.marketdata.quality import BAR_COLUMNS


def symbol_dir(root: Path, symbol: str) -> Path:
    d = root / "daily" / symbol
    d.mkdir(parents=True, exist_ok=True)
    return d


def bar_file(root: Path, symbol: str, year: int) -> Path:
    return symbol_dir(root, symbol) / f"{year}.parquet"


def adjust_file(root: Path, symbol: str) -> Path:
    d = root / "adjust"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{symbol}.parquet"


def bar_columns() -> list[str]:
    return list(BAR_COLUMNS)
