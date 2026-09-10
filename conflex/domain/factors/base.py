"""Factor 抽象基类与注册器（SDD 6.1）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

from conflex.domain.marketdata.panel import PanelData
from conflex.errors import UnknownFactor


class Factor(ABC):
    name: str = "factor"
    deps: tuple[str, ...] = ("close",)
    params: dict = {}

    @abstractmethod
    def compute(self, panel: PanelData) -> pd.DataFrame:
        """返回 index=日期、columns=股票 的因子值 DataFrame。"""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        meta = getattr(cls, "name", None)
        if meta and meta != "factor" and not getattr(cls, "__abstractmethods__", None):
            FactorRegistry.register(cls)


@dataclass
class FactorMeta:
    name: str
    cls: type
    category: str
    description: str
    deps: tuple[str, ...]
    params: dict = field(default_factory=dict)

    def create(self, **params) -> Factor:
        inst = self.cls()
        if params:
            inst.params = {**inst.params, **params}
        return inst


class FactorRegistry:
    _registry: dict[str, FactorMeta] = {}

    @classmethod
    def register(
        cls,
        factor_cls: type | None = None,
        *,
        category: str = "custom",
        description: str = "",
    ):
        def _wrap(fc):
            inst_deps = getattr(fc, "deps", ("close",))
            cls._registry[fc.name] = FactorMeta(
                name=fc.name,
                cls=fc,
                category=category,
                description=description or (fc.__doc__ or "").strip().splitlines()[0] if fc.__doc__ else "",
                deps=inst_deps,
                params=dict(getattr(fc, "params", {})),
            )
            return fc

        return _wrap(factor_cls) if factor_cls is not None else _wrap

    @classmethod
    def create(cls, name: str, **params) -> Factor:
        cls.ensure_builtins()
        if name not in cls._registry:
            raise UnknownFactor(name)
        return cls._registry[name].create(**params)

    @classmethod
    def list(cls) -> list[FactorMeta]:
        cls.ensure_builtins()
        return sorted(cls._registry.values(), key=lambda m: m.name)

    @classmethod
    def get_meta(cls, name: str) -> FactorMeta:
        cls.ensure_builtins()
        if name not in cls._registry:
            raise UnknownFactor(name)
        return cls._registry[name]

    _builtins_loaded = False

    @classmethod
    def ensure_builtins(cls):
        if not cls._builtins_loaded:
            from conflex.domain.factors import builtin  # noqa: F401  触发注册

            cls._builtins_loaded = True


def factor_cache_key(name: str, params: dict, adjust: str, universe_tag: str) -> str:
    import hashlib
    import json

    raw = json.dumps({"p": params, "a": adjust, "u": universe_tag}, sort_keys=True)
    return f"{name}__{hashlib.sha1(raw.encode()).hexdigest()[:10]}"
