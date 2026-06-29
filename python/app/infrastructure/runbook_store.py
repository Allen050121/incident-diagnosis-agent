"""Runbook store - versioned runbook storage with lifecycle management

Runbook metadata:
  runbook_id, service, component
  applicable_version, effective_from, effective_to
  owner, source_commit, content_hash, last_verified_at
  status: valid, deprecated, pending_verification

Governance rules:
  - 服务升级后，相关Runbook自动标记待验证
  - 内容哈希变化后生成新版本
  - 旧版本保留用于历史审计，运行时默认过滤
  - 超过验证时限的文档降低排序或禁止作为高置信度依据
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class RunbookStatus(Enum):
    VALID = "valid"
    DEPRECATED = "deprecated"
    PENDING_VERIFICATION = "pending_verification"
    EXPIRED = "expired"


@dataclass
class Runbook:
    runbook_id: str
    title: str
    service: str
    component: str = ""
    symptoms: list[str] = field(default_factory=list)
    root_cause: str = ""
    resolution: str = ""
    confidence_note: str = ""
    # Versioning
    version: str = "1.0"
    source_commit: str = ""
    content_hash: str = ""
    # Lifecycle
    status: RunbookStatus = RunbookStatus.VALID
    effective_from: datetime = field(default_factory=datetime.utcnow)
    effective_to: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None
    owner: str = ""
    # Tags for search
    tags: list[str] = field(default_factory=list)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Check if runbook has expired"""
        now = now or datetime.utcnow()
        if self.effective_to and now > self.effective_to:
            return True
        return False

    def needs_verification(self, max_age_days: int = 90) -> bool:
        """Check if runbook needs re-verification"""
        if self.last_verified_at is None:
            return True
        age = datetime.utcnow() - self.last_verified_at
        return age.days > max_age_days

    def is_usable_as_evidence(self) -> bool:
        """Check if runbook can be used as high-confidence evidence"""
        return (
            self.status == RunbookStatus.VALID
            and not self.is_expired()
        )

    def compute_content_hash(self) -> str:
        """Compute hash of content for change detection"""
        content = f"{self.title}|{self.root_cause}|{self.resolution}|{'|'.join(self.symptoms)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class RunbookStore:
    """In-memory runbook store with versioning and lifecycle management"""

    def __init__(self):
        self._runbooks: dict[str, list[Runbook]] = {}  # runbook_id -> [versions]

    def add(self, runbook: Runbook) -> Runbook:
        """Add a runbook (creates new version if ID exists)"""
        # Compute content hash
        runbook.content_hash = runbook.compute_content_hash()

        if runbook.runbook_id not in self._runbooks:
            self._runbooks[runbook.runbook_id] = []

        # Check if content changed from latest version
        versions = self._runbooks[runbook.runbook_id]
        if versions:
            latest = versions[-1]
            if latest.content_hash == runbook.content_hash:
                return latest  # No change

            # Mark old version as deprecated
            latest.status = RunbookStatus.DEPRECATED
            latest.effective_to = datetime.utcnow()

        versions.append(runbook)
        return runbook

    def get(self, runbook_id: str, version: str | None = None) -> Runbook | None:
        """Get a specific runbook version (or latest if version is None)"""
        versions = self._runbooks.get(runbook_id, [])
        if not versions:
            return None
        if version:
            for v in versions:
                if v.version == version:
                    return v
            return None
        return versions[-1]

    def get_active(self, runbook_id: str) -> Runbook | None:
        """Get the currently active (valid, non-expired) version"""
        versions = self._runbooks.get(runbook_id, [])
        now = datetime.utcnow()
        for v in reversed(versions):
            if v.status == RunbookStatus.VALID and not v.is_expired(now):
                return v
        return None

    def list_active(self, service: str | None = None) -> list[Runbook]:
        """List all active runbooks, optionally filtered by service"""
        result = []
        now = datetime.utcnow()
        for versions in self._runbooks.values():
            for v in reversed(versions):
                if v.status == RunbookStatus.VALID and not v.is_expired(now):
                    if service is None or v.service == service:
                        result.append(v)
                    break
        return result

    def mark_pending_verification(self, runbook_id: str, service: str | None = None):
        """Mark runbooks as pending verification (e.g., after service upgrade)"""
        versions = self._runbooks.get(runbook_id, [])
        for v in versions:
            if v.status == RunbookStatus.VALID:
                v.status = RunbookStatus.PENDING_VERIFICATION

    def mark_service_pending(self, service: str):
        """Mark all runbooks for a service as pending verification"""
        for versions in self._runbooks.values():
            for v in versions:
                if v.service == service and v.status == RunbookStatus.VALID:
                    v.status = RunbookStatus.PENDING_VERIFICATION

    def verify(self, runbook_id: str, version: str | None = None):
        """Mark a runbook as verified"""
        rb = self.get(runbook_id, version)
        if rb:
            rb.status = RunbookStatus.VALID
            rb.last_verified_at = datetime.utcnow()

    def get_all_versions(self, runbook_id: str) -> list[Runbook]:
        """Get all versions of a runbook (for audit trail)"""
        return list(self._runbooks.get(runbook_id, []))


def create_sample_runbooks() -> RunbookStore:
    """Create a store with sample runbooks for testing"""
    store = RunbookStore()

    runbooks = [
        Runbook(
            runbook_id="RB-001",
            title="MySQL Slow Query Diagnosis",
            service="order-service",
            component="mysql",
            symptoms=["slow query", "db_pool", "connection timeout", "SQLSlowQuery"],
            root_cause="Missing database index causing full table scan",
            resolution="Add index to orders.status column; optimize query plan",
            confidence_note="Verified in production incident INC-0892",
            version="1.0",
            owner="sre-team",
            last_verified_at=datetime.utcnow() - timedelta(days=10),
            tags=["database", "mysql", "slow-query", "index"],
        ),
        Runbook(
            runbook_id="RB-002",
            title="Redis Connection Timeout",
            service="order-service",
            component="redis",
            symptoms=["redis timeout", "connection pool exhausted", "RedisCommandTimeout"],
            root_cause="Redis connection pool size too small for traffic spike",
            resolution="Increase spring.redis.pool.max-active; check for slow commands",
            confidence_note="Based on incident INC-0756",
            version="1.0",
            owner="sre-team",
            last_verified_at=datetime.utcnow() - timedelta(days=30),
            tags=["redis", "timeout", "connection-pool"],
        ),
        Runbook(
            runbook_id="RB-003",
            title="Downstream Service 503",
            service="order-service",
            component="http-client",
            symptoms=["503", "service unavailable", "circuit breaker", "HttpClientErrorException"],
            root_cause="Downstream service overloaded or crashed",
            resolution="Check downstream service health; verify circuit breaker configuration",
            confidence_note="Standard procedure",
            version="1.0",
            owner="sre-team",
            last_verified_at=datetime.utcnow() - timedelta(days=5),
            tags=["downstream", "503", "circuit-breaker"],
        ),
        Runbook(
            runbook_id="RB-004",
            title="Database Connection Pool Exhaustion",
            service="order-service",
            component="hikaricp",
            symptoms=["connection pool", "HikariPool", "not available", "request timed out"],
            root_cause="Connection pool size insufficient or connections leaking",
            resolution="Increase max pool size; check for unclosed transactions; review slow queries",
            confidence_note="Common pattern in high-traffic scenarios",
            version="1.0",
            owner="sre-team",
            last_verified_at=datetime.utcnow() - timedelta(days=15),
            tags=["database", "connection-pool", "hikari", "leak"],
        ),
        Runbook(
            runbook_id="RB-005",
            title="JVM Thread Pool Saturation",
            service="order-service",
            component="jvm",
            symptoms=["thread pool", "rejected execution", "thread active high"],
            root_cause="Thread pool exhausted due to blocking operations or insufficient size",
            resolution="Increase thread pool size; identify and optimize blocking calls",
            confidence_note="Monitor jvm_threads_active metric",
            version="1.0",
            owner="sre-team",
            last_verified_at=datetime.utcnow() - timedelta(days=20),
            tags=["jvm", "thread-pool", "saturation"],
        ),
    ]

    for rb in runbooks:
        store.add(rb)

    return store
