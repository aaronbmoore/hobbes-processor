# src/schemas/project.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, List
from datetime import datetime

# Project Schemas
class ProjectBase(BaseModel):
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    is_active: bool = Field(default=True, description="Whether the project is active")

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Repository Schemas
class RepositoryBase(BaseModel):
    project_id: int = Field(..., description="ID of the project this repository belongs to")
    git_account_id: int = Field(..., description="ID of the Git account used to access this repository")
    name: str = Field(..., description="Repository name")
    repository_url: HttpUrl = Field(..., description="Full URL to the repository")
    branch: str = Field(default="main", description="Default branch to track")
    is_active: bool = Field(default=True, description="Whether the repository is active")
    file_patterns: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Patterns for including/excluding files"
    )

class RepositoryCreate(RepositoryBase):
    webhook_secret: Optional[str] = Field(None, description="Secret for webhook verification")

class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    is_active: Optional[bool] = None
    file_patterns: Optional[Dict[str, List[str]]] = None
    webhook_secret: Optional[str] = None

class RepositoryResponse(RepositoryBase):
    id: int
    created_at: datetime
    last_synced_at: Optional[datetime] = Field(None, description="Last successful sync timestamp")

    class Config:
        from_attributes = True