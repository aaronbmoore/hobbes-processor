from typing import TypedDict, List, Optional
from datetime import datetime

class GitHubAuthor(TypedDict):
    name: str
    email: str
    username: str

class GitHubCommit(TypedDict):
    id: str
    message: str
    timestamp: str
    author: GitHubAuthor
    added: List[str]
    removed: List[str]
    modified: List[str]

class PushEventPayload(TypedDict):
    ref: str
    before: str
    after: str
    repository: dict
    pusher: dict
    sender: dict
    commits: List[GitHubCommit]
    head_commit: Optional[GitHubCommit]

class RepositoryEventPayload(TypedDict):
    action: str  # 'created', 'deleted', 'archived', etc.
    repository: dict
    sender: dict

class CreateEventPayload(TypedDict):
    ref: str
    ref_type: str  # 'branch' or 'tag'
    master_branch: str
    repository: dict
    sender: dict

class DeleteEventPayload(TypedDict):
    ref: str
    ref_type: str  # 'branch' or 'tag'
    repository: dict
    sender: dict