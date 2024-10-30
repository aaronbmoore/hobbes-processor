import os
import json
import logging
import boto3
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from openai import OpenAI

logger = logging.getLogger()
logger.setLevel(logging.INFO)

@dataclass
class FileInfo:
    path: str
    sha: str
    s3_key: str
    previous_sha: Optional[str] = None

@dataclass
class RepositoryInfo:
    id: str
    url: str
    project_id: str
    git_account_id: str
    branch: str

@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str
    timestamp: str

@dataclass
class ManifestData:
    commit_info: CommitInfo
    repository: RepositoryInfo
    files: List[FileInfo]
    status: str
    created_at: str

    @classmethod
    def from_json(cls, data: Dict) -> 'ManifestData':
        return cls(
            commit_info=CommitInfo(**data['commit_info']),
            repository=RepositoryInfo(**data['repository']),
            files=[FileInfo(**f) for f in data['files']],
            status=data['status'],
            created_at=data['created_at']
        )

class APIKeyManager:
    """Manages API keys from SSM Parameter Store"""
    def __init__(self):
        self.ssm_client = boto3.client('ssm')
        self._openai_api_key: Optional[str] = None
        self._claude_api_key: Optional[str] = None

    def get_openai_api_key(self) -> str:
        if not self._openai_api_key:
            try:
                param_name = os.environ['OPENAI_API_KEY_PARAM']
                response = self.ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                self._openai_api_key = response['Parameter']['Value']
            except Exception as e:
                logger.error(f"Failed to get OpenAI API key: {str(e)}")
                raise
        return self._openai_api_key

class AnalysisProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.processing_bucket = os.environ['PROCESSING_BUCKET']
        self.api_key_manager = APIKeyManager()
        self.openai_client = None

    def init_openai(self):
        """Initialize OpenAI client with API key"""
        if not self.openai_client:
            api_key = self.api_key_manager.get_openai_api_key()
            self.openai_client = OpenAI(api_key=api_key)

    def get_embeddings(self, text: str) -> list[float]:
        """Generate embeddings for text using OpenAI API"""
        try:
            self.init_openai()
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)}")
            raise

    def process_file(self, file_content: str, file_info: FileInfo) -> None:
        """Process a single file and generate embeddings"""
        try:
            # Generate embeddings
            embeddings = self.get_embeddings(file_content)
            
            # Log success
            logger.info(f"Successfully generated embeddings for {file_info.path}")
            logger.info(f"Embedding dimensions: {len(embeddings)}")
            
            # Store embeddings in S3 for verification
            embedding_key = f"embeddings/{file_info.s3_key}.json"
            embedding_data = {
                'file_path': file_info.path,
                'embedding': embeddings,
                'generated_at': datetime.utcnow().isoformat()
            }
            
            self.s3_client.put_object(
                Bucket=self.processing_bucket,
                Key=embedding_key,
                Body=json.dumps(embedding_data).encode('utf-8')
            )

        except Exception as e:
            logger.error(f"Error processing file {file_info.path}: {str(e)}")
            raise

    def process_manifest(self, record: Dict) -> None:
        """Process an S3 event record containing a manifest"""
        try:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            if not key.startswith('manifests/') or not key.endswith('.json'):
                logger.info(f"Skipping non-manifest file: {key}")
                return
                
            logger.info(f"Processing manifest: {key}")
            
            # Get manifest from S3
            try:
                response = self.s3_client.get_object(
                    Bucket=self.processing_bucket,
                    Key=key
                )
                manifest_content = response['Body'].read().decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to retrieve manifest {key}: {str(e)}")
                raise
            
            manifest_data = ManifestData.from_json(json.loads(manifest_content))
            logger.info(f"Retrieved manifest for commit: {manifest_data.commit_info.sha}")
            
            # Process each file in manifest
            for file_info in manifest_data.files:
                try:
                    # Get file content
                    response = self.s3_client.get_object(
                        Bucket=self.processing_bucket,
                        Key=file_info.s3_key
                    )
                    file_content = response['Body'].read().decode('utf-8')
                    
                    # Process the file
                    self.process_file(file_content, file_info)
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_info.path}: {str(e)}")
                    # Continue with next file instead of failing entire manifest
                    continue
            
            # Update manifest status
            manifest_data.status = 'embeddings_generated'
            updated_manifest = {
                'commit_info': vars(manifest_data.commit_info),
                'repository': vars(manifest_data.repository),
                'files': [vars(f) for f in manifest_data.files],
                'status': manifest_data.status,
                'created_at': manifest_data.created_at,
                'analyzed_at': datetime.utcnow().isoformat()
            }
            
            self.s3_client.put_object(
                Bucket=self.processing_bucket,
                Key=key,
                Body=json.dumps(updated_manifest).encode('utf-8')
            )
            
        except Exception as e:
            logger.error(f"Error processing manifest: {str(e)}")
            raise

def handler(event: Dict, context: Any) -> Dict[str, Any]:
    """Lambda handler function"""
    processor = AnalysisProcessor()
    
    try:
        for record in event.get('Records', []):
            processor.process_manifest(record)
        
        return {
            'statusCode': 200,
            'body': 'Processing complete'
        }
    except Exception as e:
        logger.error(f"Handler failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Processing failed: {str(e)}"
        }