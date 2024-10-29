import hmac
import hashlib
from typing import Optional, Tuple, List
import re
import logging

from ..schemas.github import (
    PushEventPayload,
    RepositoryEventPayload,
    CreateEventPayload,
    DeleteEventPayload
)
from ..schemas.queue import FileChange

# Set up logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
    logger.info(f"Checking file: {file_path}")
    logger.info(f"Using patterns: {patterns}")
    
    # Get the file extension
    file_extension = file_path.split('.')[-1] if '.' in file_path else ''
    logger.info(f"File extension: {file_extension}")
    
    if not patterns:
        # Default patterns for code files - use both extensions with and without dot
        default_extensions = {'py', '.py', 'js', '.js', 'ts', '.ts', 'jsx', '.jsx', 'tsx', '.tsx', 'yml', '.yml',
                            'java', '.java', 'cpp', '.cpp', 'h', '.h', 'cs', '.cs', 'go', '.go', 
                            'rb', '.rb', 'scss', '.scss'}
        
        should_process = file_extension in default_extensions or f".{file_extension}" in default_extensions
        logger.info(f"Using default extensions. Should process: {should_process}")
        return should_process
    
    # Check include patterns
    include_patterns = patterns.get('include', [])
    if include_patterns:
        matches = [pattern for pattern in include_patterns if re.match(pattern, file_path)]
        if not matches:
            logger.info(f"File {file_path} doesn't match any include patterns: {include_patterns}")
            return False
        logger.info(f"File {file_path} matches include patterns: {matches}")
    
    # Check exclude patterns
    exclude_patterns = patterns.get('exclude', [])
    if exclude_patterns:
        matches = [pattern for pattern in exclude_patterns if re.match(pattern, file_path)]
        if matches:
            logger.info(f"File {file_path} matches exclude patterns: {matches}")
            return False
        logger.info(f"File {file_path} doesn't match any exclude patterns")
    
    logger.info(f"Will process file: {file_path}")
    return True

def extract_file_changes(payload: PushEventPayload, patterns: Optional[dict] = None) -> List[FileChange]:
    """Extract file changes from push event payload"""
    logger.info("Processing push event payload for file changes")
    logger.info(f"Using patterns: {patterns}")
    
    changes: List[FileChange] = []
    
    # Log all commits
    for commit in payload.get('commits', []):
        logger.info(f"Processing commit: {commit['id']}")
        
        # Log all files in commit
        all_files = {
            'added': commit.get('added', []),
            'modified': commit.get('modified', []),
            'removed': commit.get('removed', [])
        }
        logger.info(f"Files in commit: {all_files}")
        
        # Handle added files
        for path in commit.get('added', []):
            logger.info(f"Checking added file: {path}")
            if should_process_file(path, patterns):
                logger.info(f"Adding file change for added file: {path}")
                changes.append({
                    'path': path,
                    'sha': commit['id'],
                    'change_type': 'added',
                    'previous_sha': None
                })
        
        # Handle modified files
        for path in commit.get('modified', []):
            logger.info(f"Checking modified file: {path}")
            if should_process_file(path, patterns):
                logger.info(f"Adding file change for modified file: {path}")
                changes.append({
                    'path': path,
                    'sha': commit['id'],
                    'change_type': 'modified',
                    'previous_sha': payload.get('before')
                })
        
        # Handle removed files
        for path in commit.get('removed', []):
            logger.info(f"Checking removed file: {path}")
            if should_process_file(path, patterns):
                logger.info(f"Adding file change for removed file: {path}")
                changes.append({
                    'path': path,
                    'sha': commit['id'],
                    'change_type': 'removed',
                    'previous_sha': payload.get('before')
                })
    
    logger.info(f"Total relevant changes found: {len(changes)}")
    return changes

def get_branch_from_ref(ref: str) -> Optional[str]:
    """Extract branch name from GitHub ref"""
    if ref.startswith('refs/heads/'):
        return ref.replace('refs/heads/', '')
    return None