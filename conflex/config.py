"""全局配置（pydantic-settings 不可用时退化为 dataclass + 环境变量）。

优先级：环境变量 > conflex.yaml > 默认值（SDD 12）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:  # pragma: no cover - 取决于环境
    import yaml
except Exception:  # noqa: BLE001
    yaml = None


@dataclass
class DataSourceCfg:
    name: str
    enabled: bool = True
    priority: int = 1
    token_env: str = ""
    qps: float = 2.0
    daily_quota: int = 0

    def token(self) -> str:
        return os.getenv(self.token_env, "") if self.token_env else ""


@dataclass
class Settings:
    data_dir: str = "./data"
    market_close_time: str = "15:00"
    max_retry: int = 2
    breaker_fail_threshold: int = 5
    breaker_cooldown_seconds: int = 300
    realtime_ttl_seconds: int = 15
    web_host: str = "127.0.0.1"
    web_port: int = 8899
    jwt_expire_hours: int = 12
    jwt_secret_env: str = "CONFLEX_SECRET_KEY"
    default_broker: str = "next_open"
    commission_rate: float = 0.00025
    commission_min: float = 5.0
    stamp_tax_rate: float = 0.001
    slippage_bps: float = 5.0
    datasources: list[DataSourceCfg] = field(default_factory=list)

    # ---- 路径 ----
    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.data_path / "meta.db"

    @property
    def market_dir(self) -> Path:
        p = self.data_path / "market"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def factor_cache_dir(self) -> Path:
        p = self.data_path / "cache" / "factors"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_dir(self) -> Path:
        p = self.data_path / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def jwt_secret(self) -> bytes:
        secret = os.getenv(self.jwt_secret_env, "")
        if not secret:
            # 本机持久化的随机密钥（不入库明文配置），保证重启后 token 仍可验签
            key_file = self.data_path / ".jwt_secret"
            if key_file.exists():
                secret = key_file.read_text().strip()
            else:
                import secrets

                secret = secrets.token_urlsafe(32)
                key_file.write_text(secret)
                key_file.chmod(0o600)
        return secret.encode()


def _default_sources() -> list[DataSourceCfg]:
    return [
        DataSourceCfg("tencent", enabled=True, priority=1, qps=1),
        DataSourceCfg("sina", enabled=True, priority=2, qps=1),
        DataSourceCfg("tushare", enabled=True, priority=3, token_env="TUSHARE_TOKEN", qps=3),
        DataSourceCfg("akshare", enabled=True, priority=4, qps=1),
        DataSourceCfg("baostock", enabled=True, priority=5, qps=1),
        DataSourceCfg("efinance", enabled=True, priority=6, qps=1),
    ]


def load_settings(config_file: str | None = None) -> Settings:
    """加载配置。"""
    raw: dict = {}
    for candidate in (config_file, "conflex.yaml", str(Path.home() / ".conflex" / "conflex.yaml")):
        if candidate and Path(candidate).exists() and yaml:
            raw = yaml.safe_load(Path(candidate).read_text()) or {}
            break

    sources = [DataSourceCfg(**s) for s in raw.get("datasources", [])]
    if not sources:
        sources = _default_sources()

    flat = {
        "data_dir": raw.get("data", {}).get("dir", "./data"),
        "max_retry": raw.get("proxy", {}).get("max_retry", 2),
        "breaker_fail_threshold": raw.get("proxy", {}).get("breaker_fail_threshold", 5),
        "breaker_cooldown_seconds": raw.get("proxy", {}).get("breaker_cooldown_seconds", 300),
        "realtime_ttl_seconds": raw.get("cache", {}).get("realtime_ttl_seconds", 15),
        "web_host": raw.get("web", {}).get("host", "127.0.0.1"),
        "web_port": raw.get("web", {}).get("port", 8899),
        "jwt_expire_hours": raw.get("web", {}).get("jwt_expire_hours", 12),
    }
    flat = {k: v for k, v in flat.items() if v is not None}

    settings = Settings(datasources=sources, **flat)
    # 环境变量覆盖
    if os.getenv("CONFLEX_DATA_DIR"):
        settings.data_dir = os.environ["CONFLEX_DATA_DIR"]
    if os.getenv("CONFLEX_WEB_PORT"):
        settings.web_port = int(os.environ["CONFLEX_WEB_PORT"])
    return settings
