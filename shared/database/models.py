# src/database/models.py
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Integer, JSON, Boolean

class Base(DeclarativeBase):
    pass

class GitProvider(Base):
    __tablename__ = "git_providers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    api_base_url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GitAccount(Base):
    __tablename__ = "git_accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)
    access_token: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Project(Base):
    __tablename__ = "projects"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Repository(Base):
    __tablename__ = "repositories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer)
    git_account_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)
    repository_url: Mapped[str] = mapped_column(String)
    branch: Mapped[str] = mapped_column(String, default="main")
    webhook_secret: Mapped[str] = mapped_column(String, nullable=True)
    file_patterns: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)