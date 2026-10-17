"""SQLAlchemy persistence for the isolated workbench.

PostgreSQL is the deployment database. SQLite is deliberately supported for an
offline installation and fast, isolated integration tests.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def begin_read_snapshot(session: Session) -> None:
    """Keep multi-query PostgreSQL projections on one nonblocking MVCC view.

    Call before the session's first SQL statement. SQLite's local fallback is
    not claimed to provide the same concurrent-reader deployment guarantee.
    """
    if session.bind.dialect.name == "postgresql":
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "wb_schema_versions"
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Workspace(Base):
    __tablename__ = "wb_workspaces"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    token_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[dict] = mapped_column(JSON)
    playback: Mapped[dict] = mapped_column(JSON, default=lambda: {"playing": False, "speed": 1, "tick_minutes": 1})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "wb_audit_events"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(80))
    actor: Mapped[str] = mapped_column(String(80), default="workspace-owner")
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "wb_evidence"
    __table_args__ = (UniqueConstraint("workspace_id", "source_id", name="uq_wb_evidence_source"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(160))
    subject_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoordinationTask(Base):
    __tablename__ = "wb_tasks"
    __table_args__ = (UniqueConstraint("workspace_id", "source_id", name="uq_wb_task_source"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40))
    owner_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class CoordinationRequest(Base):
    __tablename__ = "wb_coordination_requests"
    __table_args__ = (CheckConstraint("status IN ('open', 'in_progress', 'resolved')", name="ck_wb_request_status"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), ForeignKey("wb_workspaces.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    owner_role: Mapped[str] = mapped_column(String(80))
    service_kind: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    comment: Mapped[str] = mapped_column(Text, default="")
    container_ids: Mapped[list] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "wb_jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    input_revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    state_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "wb_idempotency"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_wb_idempotency_key"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scope: Mapped[str] = mapped_column(String(240))
    key: Mapped[str] = mapped_column(String(200))
    body_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderInbox(Base):
    __tablename__ = "wb_provider_inbox"
    __table_args__ = (UniqueConstraint("connection", "event_id", name="uq_wb_provider_event"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    connection: Mapped[str] = mapped_column(String(80))
    event_id: Mapped[str] = mapped_column(String(160))
    body_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="received")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Database:
    def __init__(self, url: str):
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 20}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
        self.url = url
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def sqlite_constraints(connection, record):
                connection.execute("PRAGMA foreign_keys=ON")
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        # SQLite has no row-level SELECT FOR UPDATE. This protects local demo
        # requests, while the revision CAS is still checked in the database.
        self.write_lock = threading.RLock()

    def initialize(self) -> None:
        from alembic import command
        from alembic.config import Config
        configuration = Config()
        configuration.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(748210529)"))
            configuration.attributes["connection"] = connection
            inspector = inspect(connection)
            existing = set(inspector.get_table_names())
            # Adopt only an exact, already-created development schema. Do not
            # stamp an unknown partial schema and pretend its migration ran.
            if "wb_alembic_version" not in existing and set(Base.metadata.tables).issubset(existing):
                for table_name, table in Base.metadata.tables.items():
                    actual = {column["name"] for column in inspector.get_columns(table_name)}
                    if not set(table.columns.keys()).issubset(actual):
                        raise RuntimeError("An incomplete workbench schema needs an explicit migration; existing data was not changed.")
                command.stamp(configuration, "head")
            command.upgrade(configuration, "head")
        with self.session() as session:
            if session.get(SchemaVersion, "workbench-1") is None:
                session.add(SchemaVersion(version="workbench-1"))
            if session.get(SchemaVersion, "workbench-2") is None:
                session.add(SchemaVersion(version="workbench-2"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.sessions.begin() as session:
            yield session

    def ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


_database: Database | None = None
_database_lock = threading.Lock()


def configure_database(url: str | None = None) -> Database:
    global _database
    with _database_lock:
        if _database is not None:
            _database.engine.dispose()
        if url is None:
            url = os.getenv("WORKBENCH_DATABASE_URL")
        if not url:
            folder = Path(__file__).resolve().parents[2] / ".local"
            folder.mkdir(exist_ok=True)
            url = f"sqlite:///{folder / 'workbench.db'}"
        _database = Database(url)
        _database.initialize()
        return _database


def get_database() -> Database:
    return _database if _database is not None else configure_database()
