from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

project_config=Path(__file__).resolve().parents[1] / ".env"
local_config=Path(os.getenv("LOCALAPPDATA",str(Path.cwd()/".runtime"))) / "Ternfold" / ".env"
load_dotenv(Path(os.getenv("TERNFOLD_CONFIG_FILE",str(local_config))))
load_dotenv(project_config,override=False)

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
    return value

engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

def init_database() -> None:
    from . import models  # noqa
    Base.metadata.create_all(engine)

