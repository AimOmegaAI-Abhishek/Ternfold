from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from collections.abc import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

project_config=Path(__file__).resolve().parents[1] / ".env"
local_config=Path(os.getenv("LOCALAPPDATA",str(Path.cwd()/".runtime"))) / "Ternfold" / ".env"
load_dotenv(Path(os.getenv("TERNFOLD_CONFIG_FILE",str(local_config))), encoding="utf-8-sig")
load_dotenv(project_config,override=False, encoding="utf-8-sig")

class Base(DeclarativeBase):
    pass

def database_url() -> str:
    value = os.getenv("SUPABASE_DATABASE_URL")
    if not value:
        raise RuntimeError("SUPABASE_DATABASE_URL is required. Ternfold does not support a local database.")
    if value.startswith("postgres://"):
        value = "postgresql://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://") and "+psycopg" not in value:
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    url=make_url(value)
    if not url.host or not url.host.endswith((".supabase.co", ".pooler.supabase.com")):
        raise RuntimeError("Use the Supabase database connection URL. Other database hosts are not supported.")
    return url.update_query_dict({"sslmode":"require","connect_timeout":"10"}).render_as_string(hide_password=False)

engine = create_engine(database_url(), pool_pre_ping=True, poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

def init_database() -> None:
    from . import models  # noqa
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        schema=connection.scalar(text("select current_schema()"))
        for table in Base.metadata.sorted_tables:
            quote=connection.dialect.identifier_preparer.quote
            connection.execute(text(f"ALTER TABLE {quote(schema)}.{quote(table.name)} ENABLE ROW LEVEL SECURITY"))
