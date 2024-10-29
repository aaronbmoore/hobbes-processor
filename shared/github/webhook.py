import hmac
import hashlib
from typing import Optional, Tuple, List
import re

from ..schemas.github import (
    PushEventPayload,
    RepositoryEventPayload,
    CreateEventPayload,
    DeleteEventPayload
)
from ..schemas.queue import FileChange

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature or not secret:
        return False
        
    expected_signature = 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def should_process_file(file_path: str, patterns: Optional[dict] = None) -> bool:
    """Determine if a file should be processed based on patterns"""
    if not patterns:
        # Default patterns for code files
        default_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.h', '.cs', '.go', '.rb'}
        return any(file_path.endswith(ext) for ext in default_extensions)
    
    # Check include patterns
    include_patterns = patterns.get('include', [])
    if include_patterns:
        if not any(re.match(pattern, file_path) for pattern in include_patterns):
            return False
    
    # Check exclude patterns
    exclude_patterns = patterns.get('exclude', [])
    if exclude_patterns:
        if any(re.match(pattern, file_path) for pattern in exclude_patterns):
            return False
    
    return True

def extract_file_changes(payload: PushEventPayload, patterns: Optional[dict] = None) -> List[FileChange]:
    """Extract file changes from push event payload"""
    changes: List[FileChange] = []
    
    for commit in payload['commits']:
        # Handle added files
        for path in commit['added']:
            if should_process_file(path, patterns):
                changes.append({
                    'path': path,
                    'sha': commit['id'],
                    'change_type': 'added',
                    'previous_sha': None
                })
        
        # Handle modified files
        for path in commit['modified']:
            if should_process_file(path, patterns):
                changes.append({
                    'path': path,
                    'sha': commit['id'],
                    'change_type': 'modified',
                    'previous_sha': payload['before']
                })
        
        # Handle removed files
        for path in commit['removed']:
            if should_process_file(path, patterns):
                changes.append({
                    'path': path,
                    'sha': commit['id'],
                    'change_type': 'removed',
                    'previous_sha': payload['before']
                })
    
    return changes

def get_branch_from_ref(ref: str) -> Optional[str]:
    """Extract branch name from GitHub ref"""
    if ref.startswith('refs/heads/'):
        return ref.replace('refs/heads/', '')
    return None