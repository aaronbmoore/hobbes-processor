import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.validation import validate_event_schema
from aws_lambda_powertools.event_handler.api_gateway import ApiGatewayResolver, Response

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

# Initialize Logger and Tracer
logger = Logger()
tracer = Tracer()

class WebhookHandler:
    def __init__(self):
        self.sqs_handler = SQSHandler(os.environ['FILE_PROCESSING_QUEUE_URL'])
    
    @tracer.capture_method
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
        message_id = await self.sqs_handler.send_message(message)
        logger.info(f"Queued message {message_id} for repository {repo.id}")
        return message_id
    
    @tracer.capture_method
    async def process_create_event(
        self,
        payload: CreateEventPayload,
        repo: Repository,
        account: GitAccount
    ) -> Optional[str]:
        """Process create event (new branch/tag)"""
        if payload['ref_type'] != 'branch' or payload['ref'] != repo.branch:
            logger.info(f"Skipping create event for {payload['ref_type']} {payload['ref']}")
            return None
            
        # Queue full repository scan for new branch
        message = create_setup_message(
            repository_id=repo.id,
            project_id=repo.project_id,
            git_account_id=account.id,
            repository_url=repo.repository_url,
            branch=payload['ref']
        )
        
        message_id = await self.sqs_handler.send_message(message)
        logger.info(f"Queued setup message {message_id} for repository {repo.id}")
        return message_id
    
    @tracer.capture_method
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
            logger.warning(f"Invalid webhook signature for repository {repo.id}")
            return Response(
                status_code=401,
                body={"error": "Invalid webhook signature"}
            ).dict()
        
        # Parse payload
        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON payload for repository {repo.id}")
            return Response(
                status_code=400,
                body={"error": "Invalid JSON payload"}
            ).dict()
         
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
            
            return Response(
                status_code=200,
                body={
                    "status": "success",
                    "message_id": message_id
                }
            ).dict()
            
        except Exception as e:
            logger.exception(f"Error processing webhook for repository {repo.id}")
            return Response(
                status_code=500,
                body={"error": "Internal server error"}
            ).dict()

@logger.inject_lambda_context
@tracer.capture_lambda_handler
async def handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda handler function"""
    try:
        # Extract repository ID from path parameters
        repo_id = event.get('pathParameters', {}).get('repo_id')
        if not repo_id:
            logger.error("Missing repository ID in path parameters")
            return Response(
                status_code=400,
                body={"error": "Missing repository ID"}
            ).dict()
        
        # Get webhook details
        signature = event.get('headers', {}).get('X-Hub-Signature-256', '')
        event_type = event.get('headers', {}).get('X-GitHub-Event', '')
        payload = event.get('body', '').encode()
        
        if not signature or not event_type:
            logger.error(f"Missing required headers for repository {repo_id}")
            return Response(
                status_code=400,
                body={"error": "Missing required headers"}
            ).dict()
        
        # Get repository and account details
        async with get_db_session() as session:
            repo = await session.get(Repository, repo_id)
            if not repo or not repo.is_active:
                logger.warning(f"Repository {repo_id} not found or inactive")
                return Response(
                    status_code=404,
                    body={"error": "Repository not found"}
                ).dict()
            
            account = await session.get(GitAccount, repo.git_account_id)
            if not account or not account.is_active:
                logger.warning(f"Git account {repo.git_account_id} not found or inactive")
                return Response(
                    status_code=404,
                    body={"error": "Git account not found"}
                ).dict()
            
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
        logger.exception("Unhandled error in webhook handler")
        return Response(
            status_code=500,
            body={"error": "Internal server error"}
        ).dict()