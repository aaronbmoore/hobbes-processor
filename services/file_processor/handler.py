import os
import json
import logging
import boto3
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_async_session
from shared.github.client import GitHubClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize CloudWatch client
cloudwatch = boto3.client('cloudwatch')

@dataclass
class FileChange:
    path: str
    sha: str
    change_type: str
    previous_sha: Optional[str] = None

@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str
    timestamp: str

@dataclass
class ProcessingPayload:
    repository_id: str
    project_id: str
    git_account_id: str
    repository_url: str
    branch: str
    commit_info: CommitInfo
    file_changes: List[FileChange]

    @classmethod
    def from_sqs_message(cls, message_body: Dict) -> 'ProcessingPayload':
        return cls(
            repository_id=message_body['repository_id'],
            project_id=message_body['project_id'],
            git_account_id=message_body['git_account_id'],
            repository_url=message_body['repository_url'],
            branch=message_body['branch'],
            commit_info=CommitInfo(**message_body['commit_info']),
            file_changes=[FileChange(**fc) for fc in message_body['file_changes']]
        )

class FileProcessorError(Exception):
    """Base class for file processor errors"""
    pass

class GitHubError(FileProcessorError):
    """GitHub API related errors"""
    pass

class S3Error(FileProcessorError):
    """S3 operation errors"""
    pass

class FileProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.sqs_client = boto3.client('sqs')
        self.github_client = GitHubClient()
        self.processing_bucket = os.environ['PROCESSING_BUCKET']
        self.queue_url = os.environ['FILE_PROCESSING_QUEUE_URL']
        self.max_retries = int(os.environ.get('MAX_RETRIES', '3'))
        self.service_name = os.environ.get('POWERTOOLS_SERVICE_NAME', 'file-processor')

    async def emit_metric(self, metric_name: str, value: float = 1, unit: str = 'Count', dimensions: Optional[List[Dict]] = None):
        """Emit CloudWatch metric"""
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Dimensions': dimensions or [
                    {'Name': 'Service', 'Value': self.service_name}
                ]
            }
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: cloudwatch.put_metric_data(
                    Namespace='CodeAssistant',
                    MetricData=[metric_data]
                )
            )
        except Exception as e:
            logger.error(f"Failed to emit metric {metric_name}: {e}")

    async def process_message(self, message: Dict, db_session: AsyncSession) -> None:
        message_id = message.get('MessageId', 'unknown')
        processing_start = datetime.utcnow()
        
        try:
            payload = ProcessingPayload.from_sqs_message(json.loads(message['Body']))
            
            manifest = {
                'commit_info': {
                    'sha': payload.commit_info.sha,
                    'message': payload.commit_info.message,
                    'author': payload.commit_info.author,
                    'timestamp': payload.commit_info.timestamp
                },
                'repository': {
                    'id': payload.repository_id,
                    'url': payload.repository_url,
                    'project_id': payload.project_id,
                    'git_account_id': payload.git_account_id,
                    'branch': payload.branch
                },
                'files': [],
                'status': 'pending',
                'created_at': datetime.utcnow().isoformat(),
            }

            files_processed = 0
            files_failed = 0
            
            for file_change in payload.file_changes:
                if file_change.change_type != 'removed':
                    try:
                        content = await self.github_client.get_file_content(
                            session=db_session,
                            git_account_id=payload.git_account_id,
                            repo_url=payload.repository_url,
                            file_path=file_change.path,
                            ref=file_change.sha
                        )
                        
                        s3_key = f"files/{payload.commit_info.sha}/{file_change.path}"
                        
                        await self.upload_to_s3(
                            key=s3_key,
                            content=content,
                            metadata={
                                'repository_id': payload.repository_id,
                                'commit_sha': payload.commit_info.sha,
                                'file_sha': file_change.sha
                            }
                        )
                        
                        manifest['files'].append({
                            'path': file_change.path,
                            'sha': file_change.sha,
                            'previous_sha': file_change.previous_sha,
                            's3_key': s3_key
                        })
                        
                        files_processed += 1
                        await self.emit_metric('FilesProcessed')
                        
                    except Exception as e:
                        files_failed += 1
                        await self.emit_metric('FileProcessingErrors')
                        logger.error(f"Error processing file {file_change.path}: {str(e)}")
                        await self.handle_file_error(message, file_change, e)
                        continue
            
            if manifest['files']:
                manifest_key = f"manifests/{payload.commit_info.sha}.json"
                await self.upload_to_s3(
                    key=manifest_key,
                    content=json.dumps(manifest),
                    metadata={
                        'repository_id': payload.repository_id,
                        'commit_sha': payload.commit_info.sha
                    }
                )
                
                await self.delete_message(message)
                await self.emit_metric('CommitsProcessed')
            else:
                logger.warning(f"No files processed for commit {payload.commit_info.sha}")
                await self.delete_message(message)

            # Emit processing duration metric
            processing_duration = (datetime.utcnow() - processing_start).total_seconds()
            await self.emit_metric('ProcessingDuration', value=processing_duration, unit='Seconds')
                
        except json.JSONDecodeError as e:
            await self.emit_metric('MessageFormatErrors')
            logger.error(f"Invalid message format: {e}")
            await self.handle_message_error(message, e, recoverable=False)
        except Exception as e:
            await self.emit_metric('MessageProcessingErrors')
            logger.error(f"Error processing message: {e}")
            await self.handle_message_error(message, e)

    async def upload_to_s3(self, key: str, content: str, metadata: Dict) -> None:
        retries = 0
        while retries < self.max_retries:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.s3_client.put_object(
                        Bucket=self.processing_bucket,
                        Key=key,
                        Body=content.encode('utf-8'),
                        Metadata=metadata
                    )
                )
                await self.emit_metric('S3Uploads')
                return
            except Exception as e:
                retries += 1
                await self.emit_metric('S3Errors')
                if retries >= self.max_retries:
                    raise S3Error(f"Failed to upload to S3 after {retries} attempts: {e}")
                await asyncio.sleep(2 ** retries)  # Exponential backoff

    async def delete_message(self, message: Dict) -> None:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.sqs_client.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=message['ReceiptHandle']
                )
            )
        except Exception as e:
            await self.emit_metric('SQSErrors')
            logger.error(f"Error deleting SQS message: {e}")

    async def handle_file_error(self, message: Dict, file_change: FileChange, error: Exception) -> None:
        error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'file_path': file_change.path,
            'sha': file_change.sha,
            'timestamp': datetime.utcnow().isoformat()
        }

        try:
            error_key = f"errors/{file_change.sha}/{file_change.path}.json"
            await self.upload_to_s3(
                key=error_key,
                content=json.dumps(error_details),
                metadata={'error_type': type(error).__name__}
            )
        except Exception as e:
            logger.error(f"Failed to save error details: {e}")

    async def handle_message_error(self, message: Dict, error: Exception, recoverable: bool = True) -> None:
        message_id = message.get('MessageId', 'unknown')
        error_count = int(message.get('Attributes', {}).get('ApproximateReceiveCount', 1))

        logger.error(f"Message {message_id} failed processing: {error}")

        if not recoverable or error_count >= self.max_retries:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.sqs_client.send_message(
                        QueueUrl=os.environ['DLQ_URL'],
                        MessageBody=json.dumps({
                            'original_message': message,
                            'error': str(error),
                            'error_type': type(error).__name__,
                            'attempts': error_count,
                            'timestamp': datetime.utcnow().isoformat()
                        })
                    )
                )
                await self.delete_message(message)
                await self.emit_metric('MessagesSentToDLQ')
            except Exception as e:
                logger.error(f"Failed to move message to DLQ: {e}")

async def handler(event: Dict, context: Any) -> Dict:
    processor = FileProcessor()
    
    async with get_async_session() as session:
        for record in event.get('Records', []):
            await processor.process_message(record, session)
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Processing complete'})
    }

async def process_event(event: Dict, context: Any) -> Dict:
    processor = FileProcessor()
    
    try:
        async with get_async_session() as session:
            for record in event.get('Records', []):
                await processor.process_message(record, session)
    finally:
        # Ensure aiohttp session is closed
        if hasattr(processor, 'github_client'):
            await processor.github_client.close()

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Processing complete'})
    }

def lambda_handler(event: Dict, context: Any) -> Dict:
    """AWS Lambda entry point"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(process_event(event, context))