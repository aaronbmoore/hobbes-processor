from typing import TypedDict, List, Optional
from datetime import datetime

class FileChange(TypedDict):
    """Represents a single file change in a commit"""
    path: str
    sha: str
    change_type: str  # 'added', 'modified', 'removed'
    previous_sha: Optional[str]  # For tracking changes

class CommitInfo(TypedDict):
    """Information about a commit"""
    sha: str
    message: str
    author: str
    timestamp: str

class QueueMessage(TypedDict):
    """Message format for SQS queue between webhook and file processor"""
    # Repository identification
    repository_id: int
    project_id: int
    git_account_id: int
    repository_url: str
    branch: str
    
    # Event information
    event_type: str  # 'push', 'create', 'delete', 'repository'
    event_timestamp: str
    
    # For push events
    commit_info: Optional[CommitInfo]
    file_changes: List[FileChange]
    
    # For repository setup
    full_scan: bool  # True for initial repository setup
    
    # For delete events
    deleted_ref: Optional[str]  # Branch or tag name that was deleted