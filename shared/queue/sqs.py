import json
import boto3
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class SQSHandler:
    def __init__(self, queue_url: str):
        self.queue_url = queue_url
        self.sqs = boto3.client('sqs')
        logger.info(f"Initialized SQS handler with queue URL: {queue_url}")
    
    def send_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Send message to SQS queue"""
        try:
            logger.info(f"Sending message to SQS: {json.dumps(message)}")
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message)
            )
            logger.info(f"Message sent successfully: {response['MessageId']}")
            return response['MessageId']
            
        except Exception as e:
            logger.error(f"Error sending message to SQS: {str(e)}")
            raise

    def send_batch_messages(self, messages: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict]]:
        """Send batch of messages to SQS queue"""
        try:
            logger.info(f"Sending batch of {len(messages)} messages to SQS")
            entries = [
                {
                    'Id': str(i),
                    'MessageBody': json.dumps(message)
                }
                for i, message in enumerate(messages)
            ]
            
            response = self.sqs.send_message_batch(
                QueueUrl=self.queue_url,
                Entries=entries
            )
            
            # Track successful and failed messages
            successful = [msg['MessageId'] for msg in response.get('Successful', [])]
            failed = response.get('Failed', [])
            
            logger.info(f"Batch send complete. Successful: {len(successful)}, Failed: {len(failed)}")
            if failed:
                logger.warning(f"Failed messages: {json.dumps(failed)}")
                
            return successful, failed
            
        except Exception as e:
            logger.error(f"Error sending batch messages to SQS: {str(e)}")
            raise