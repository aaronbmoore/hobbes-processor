import os
import json
import logging
import boto3
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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

class FileProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.sqs_client = boto3.client('sqs')
        self.processing_bucket = os.environ['PROCESSING_BUCKET']
        self.queue_url = os.environ['FILE_PROCESSING_QUEUE_URL']
        
    async def process_message(self, message: Dict) -> None:
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
            
            for file_change in payload.file_changes:
                if file_change.change_type != 'removed':
                    try:
                        # TODO: Implement GitHub file content retrieval
                        content = "TODO: Get file content from GitHub"
                        
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
                        
                    except Exception as e:
                        logger.error(f"Error processing file {file_change.path}: {str(e)}")
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
            else:
                logger.warning(f"No files processed for commit {payload.commit_info.sha}")
                await self.delete_message(message)
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")

    async def upload_to_s3(self, key: str, content: str, metadata: Dict) -> None:
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
        except Exception as e:
            logger.error(f"S3 upload error for key {key}: {str(e)}")
            raise

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
            logger.error(f"Error deleting SQS message: {str(e)}")

def handler(event: Dict, context: Any) -> Dict[str, Any]:
    processor = FileProcessor()
    
    async def process():
        for record in event.get('Records', []):
            await processor.process_message(record)

    asyncio.run(process())
    return {
        'statusCode': 200,
        'body': 'Processing complete'
    }