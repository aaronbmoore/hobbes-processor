import json
import os
import logging
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
        # Verify this is a branch push (not a tag)
        branch = get_branch_from_ref(payload['ref'])
        if not branch or branch != repo.branch:
            logger.info(f"Skipping push event for ref {payload['ref']}")
            return None
        
        # Extract file changes
        file_changes = extract_file_changes(payload, repo.file_patterns)
        if not file_changes:
            logger.info("No relevant file changes found")
            return None
        
        # Create queue message
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
        
        # Queue message
        return await self.sqs_handler.send_message(message)
    
    async def process_create_event(
        self,
        payload: CreateEventPayload,
        repo: Repository,
        account: GitAccount
    ) -> Optional[str]:
        """Process create event (new branch/tag)"""
        if payload['ref_type'] != 'branch' or payload['ref'] != repo.branch:
            return None
            
        # Queue full repository scan for new branch
        message = create_setup_message(
            repository_id=repo.id,
            project_id=repo.project_id,
            git_account_id=account.id,
            repository_url=repo.repository_url,
            branch=payload['ref']
        )
        
        return await self.sqs_handler.send_message(message)
    
    async def handle_webhook(
        self,
        event_type: str,
        signature: str,
        payload: bytes,
        repo: Repository,
        account: GitAccount
    ) -> Dict[str, Any]:
        """Handle webhook event"""
        # Verify webhook signature
        if not verify_signature(payload, signature, repo.webhook_secret):
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Invalid webhook signature'})
            }
        
        # Parse payload
        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid JSON payload'})
            }
         
        try:
            message_id = None
            
            # Process based on event type
            if event_type == 'push':
                message_id = await self.process_push_event(
                    payload_dict,
                    repo,
                    account
                )
            elif event_type == 'create':
                message_id = await self.process_create_event(
                    payload_dict,
                    repo,
                    account
                )
            # Add other event types as needed
            
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

async def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler function"""
    try:
        # Extract repository ID from path parameters
        repo_id = event['pathParameters']['repo_id']
        
        # Get webhook details
        signature = event['headers'].get('X-Hub-Signature-256', '')
        event_type = event['headers'].get('X-GitHub-Event', '')
        payload = event['body'].encode()
        
        # Get repository and account details
        async with get_db_session() as session:
            repo = await session.get(Repository, repo_id)
            if not repo or not repo.is_active:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Repository not found'})
                }
            
            account = await session.get(GitAccount, repo.git_account_id)
            if not account or not account.is_active:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Git account not found'})
                }
            
            # Process webhook
            webhook_handler = WebhookHandler()
            return await webhook_handler.handle_webhook(
                event_type,
                signature,
                payload,
                repo,
                account
            )
            
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }