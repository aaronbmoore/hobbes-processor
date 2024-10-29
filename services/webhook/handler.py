import json
import os
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from shared.database.session import get_db_session
from shared.database.models import Repository, GitAccount
from shared.schemas.github import (
    PushEventPayload,
    RepositoryEventPayload,
    CreateEventPayload,
    DeleteEventPayload
)
from shared.github.webhook import (
    verify_signature,
    extract_file_changes,
    get_branch_from_ref
)
from shared.queue.sqs import SQSHandler
from shared.queue.messages import create_push_event_message, create_setup_message

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class WebhookHandler:
    def __init__(self):
        self.sqs_handler = SQSHandler(os.environ['FILE_PROCESSING_QUEUE_URL'])
    
    async def process_push_event(
        self,
        payload: PushEventPayload,
        repo: Repository,
        account: GitAccount
    ) -> Optional[str]:
        """Process push event and queue for file processing"""
        branch = get_branch_from_ref(payload['ref'])
        if not branch or branch != repo.branch:
            logger.info(f"Skipping push event for ref {payload['ref']}")
            return None
        
        file_changes = extract_file_changes(payload, repo.file_patterns)
        if not file_changes:
            logger.info("No relevant file changes found")
            return None
        
        message = create_push_event_message(
            repository_id=repo.id,
            project_id=repo.project_id,
            git_account_id=account.id,
            repository_url=repo.repository_url,
            branch=branch,
            commit_info={
                'sha': payload['after'],
                'message': payload['head_commit']['message'],
                'author': payload['head_commit']['author']['name'],
                'timestamp': payload['head_commit']['timestamp']
            },
            file_changes=file_changes
        )
        
        return self.sqs_handler.send_message(message)
    
    async def handle_webhook(
        self,
        event_type: str,
        signature: Optional[str],
        payload: bytes,
        repo: Repository,
        account: GitAccount
    ) -> Dict[str, Any]:
        """Handle webhook event"""
        # Only verify signature if webhook secret is configured
        if repo.webhook_secret and signature:
            if not verify_signature(payload, signature, repo.webhook_secret):
                return {
                    'statusCode': 401,
                    'body': json.dumps({'error': 'Invalid webhook signature'})
                }
        
        try:
            payload_dict = json.loads(payload)
            message_id = None
            
            if event_type == 'push':
                message_id = await self.process_push_event(
                    payload_dict,
                    repo,
                    account
                )
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'message_id': message_id
                })
            }
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Internal server error'})
            }


async def _handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Async handler implementation"""
    try:
        # Log the incoming event for debugging
        logger.info(f"Received event: {json.dumps(event, default=str)}")
        
        # Get webhook details
        headers = event.get('headers', {})
        # Check for both upper and lowercase header names
        event_type = headers.get('X-GitHub-Event') or headers.get('x-github-event')
        signature = headers.get('X-Hub-Signature-256') or headers.get('x-hub-signature-256')
        
        if not event_type:
            logger.error("Missing GitHub Event header")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing GitHub Event header',
                    'received_headers': headers
                })
            }

        payload = event.get('body', '')
        if not payload:
            logger.error("Empty payload received")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Empty payload'})
            }

        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid JSON payload'})
            }

        # Get repository information from the payload
        repository_url = payload_dict.get('repository', {}).get('html_url')
        if not repository_url:
            logger.error("No repository URL in payload")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing repository information'})
            }
        
        # Find repository in database
        async with get_db_session() as session:
            from sqlalchemy import select
            # Query by repository URL
            repo = await session.execute(
                select(Repository).where(Repository.repository_url == repository_url)
            )
            repo = repo.scalar_one_or_none()
            
            if not repo or not repo.is_active:
                logger.warning(f"Repository not found: {repository_url}")
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Repository not found'})
                }
            
            account = await session.get(GitAccount, repo.git_account_id)
            if not account or not account.is_active:
                logger.warning(f"Git account not found: {repo.git_account_id}")
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Git account not found'})
                }
            
            webhook_handler = WebhookHandler()
            return await webhook_handler.handle_webhook(
                event_type,
                signature,
                payload.encode(),
                repo,
                account
            )
            
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler function that properly handles async execution"""
    return asyncio.run(_handler(event, context))