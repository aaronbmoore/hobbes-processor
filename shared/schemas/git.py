# src/schemas/git.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, List
from datetime import datetime

# Git Provider Schemas
class GitProviderBase(BaseModel):
    name: str = Field(..., description="Name of the Git provider (e.g., 'GitHub', 'GitLab')")
    api_base_url: HttpUrl = Field(..., description="Base URL for the provider's API")

class GitProviderCreate(GitProviderBase):
    pass

class GitProviderResponse(GitProviderBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Git Account Schemas
class GitAccountBase(BaseModel):
    name: str = Field(..., description="Friendly name for the account")
    provider_id: int = Field(..., description="ID of the Git provider")
    is_active: bool = Field(default=True, description="Whether the account is active")

class GitAccountCreate(GitAccountBase):
    access_token: str = Field(..., description="OAuth token or Personal Access Token")

class GitAccountUpdate(BaseModel):
    name: Optional[str] = None
    access_token: Optional[str] = None
    is_active: Optional[bool] = None

class GitAccountResponse(GitAccountBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True