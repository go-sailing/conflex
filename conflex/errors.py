"""统一异常体系（详见 SDD 13.1）。"""


class ConflexError(Exception):
    """所有受控异常的基类。"""

    code = "conflex_error"
    http_status = 400


class DomainError(ConflexError):
    code = "domain_error"


class InvalidOrderTransition(DomainError):
    code = "invalid_order_transition"


class InsufficientCash(DomainError):
    code = "insufficient_cash"


class InsufficientPosition(DomainError):
    code = "insufficient_position"


class InvalidConfig(DomainError):
    code = "invalid_config"


# ---- 数据层 ----
class DataError(ConflexError):
    code = "data_error"
    http_status = 502


class SourceError(DataError):
    """数据源错误基类，kind 决定是否重试/换源。"""

    kind = "source_error"
    retriable = False

    def __init__(self, source: str = "", message: str = ""):
        self.source = source
        super().__init__(message or f"{source} 数据源错误")


class SourceNetworkError(SourceError):
    kind, retriable = "network", True


class SourceRateLimit(SourceError):
    kind, retriable = "rate_limit", True


class SourceAuthError(SourceError):
    kind, retriable = "auth", False


class SourceEmpty(SourceError):
    kind, retriable = "empty", False


class SourceBadRequest(SourceError):
    kind, retriable = "bad_request", False


class QualityError(DataError):
    code = "quality_error"

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


class AllSourcesExhausted(DataError):
    code = "all_sources_exhausted"

    def __init__(self, attempts: list[tuple[str, str]]):
        self.attempts = attempts
        super().__init__("所有数据源均失败：" + ", ".join(f"{s}:{r}" for s, r in attempts))


# ---- 因子 ----
class FactorError(ConflexError):
    code = "factor_error"


class UnknownFactor(FactorError):
    code = "unknown_factor"


# ---- 回测 ----
class BacktestError(ConflexError):
    code = "backtest_error"


class LeakageError(BacktestError):
    """读取到未来数据（防未来函数断言）。"""

    code = "future_leakage"


# ---- 基础设施 ----
class InfraError(ConflexError):
    code = "infra_error"
    http_status = 500


class StorageError(InfraError):
    code = "storage_error"
