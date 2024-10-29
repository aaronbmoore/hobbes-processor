from datetime import datetime
from typing import List

from ..schemas.queue import QueueMessage, CommitInfo, FileChange

def create_push_event_message(
    repository_id: int,
    project_id: int,
    git_account_id: int,
    repository_url: str,
    branch: str,
    commit_info: CommitInfo,
    file_changes: List[FileChange]
) -> QueueMessage:
    """Helper function to create a push event message"""
    return {
        "repository_id": repository_id,
        "project_id": project_id,
        "git_account_id": git_account_id,
        "repository_url": repository_url,
        "branch": branch,
        "event_type": "push",
        "event_timestamp": datetime.utcnow().isoformat(),
        "commit_info": commit_info,
        "file_changes": file_changes,
        "full_scan": False,
        "deleted_ref": None
    }

def create_setup_message(
    repository_id: int,
    project_id: int,
    git_account_id: int,
    repository_url: str,
    branch: str
) -> QueueMessage:
    """Helper function to create an initial setup message"""
    return {
        "repository_id": repository_id,
        "project_id": project_id,
        "git_account_id": git_account_id,
        "repository_url": repository_url,
        "branch": branch,
        "event_type": "setup",
        "event_timestamp": datetime.utcnow().isoformat(),
        "commit_info": None,
        "file_changes": [],
        "full_scan": True,
        "deleted_ref": None
    }