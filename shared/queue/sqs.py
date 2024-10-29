import json
import boto3
from typing import Any, Optional
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

class SQSHandler:
    def __init__(self, queue_url: str):
        self.sqs = boto3.client('sqs')
        self.queue_url = queue_url
    
    async def send_message(self, message: dict) -> Optional[str]:
        """Send message to SQS queue"""
        try:
            response = await self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message)
            )
            return response.get('MessageId')
        except ClientError as e:
            logger.error(f"Failed to send message to SQS: {e}")
            raise
    
    async def send_batch_messages(self, messages: list[dict]) -> tuple[list[str], list[dict]]:
        """Send batch of messages to SQS queue"""
        try:
            entries = [
                {
                    'Id': str(i),
                    'MessageBody': json.dumps(message)
                }
                for i, message in enumerate(messages)
            ]
            
            response = await self.sqs.send_message_batch(
                QueueUrl=self.queue_url,
                Entries=entries
            )
            
            # Track successful and failed messages
            successful = [msg['MessageId'] for msg in response.get('Successful', [])]
            failed = response.get('Failed', [])
            
            return successful, failed
            
        except ClientError as e:
            logger.error(f"Failed to send batch messages to SQS: {e}")
            raise