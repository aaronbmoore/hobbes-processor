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
    def __init__(self):
        self.ssm_client = boto3.client('ssm')
        self._openai_api_key: Optional[str] = None

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
        logger.info(f"Initialized AnalysisProcessor with bucket: {self.processing_bucket}")
        self.api_key_manager = APIKeyManager()
        self.openai_client = None

    def init_openai(self):
        try:
            if not self.openai_client:
                api_key = self.api_key_manager.get_openai_api_key()
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("Successfully initialized OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def get_embeddings(self, text: str) -> list[float]:
        try:
            self.init_openai()
            logger.info(f"Generating embeddings for text length: {len(text)}")
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            embeddings = response.data[0].embedding
            logger.info(f"Generated embeddings with dimensions: {len(embeddings)}")
            logger.info(f"Sample of embeddings (first 5 values): {embeddings[:5]}")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)}")
            raise

    def process_file(self, file_content: str, file_info: FileInfo) -> None:
        try:
            logger.info(f"Processing file: {file_info.path}")
            logger.info(f"Content length: {len(file_content)}")
            logger.info(f"File SHA: {file_info.sha}")
            
            embeddings = self.get_embeddings(file_content)
            
            # Log successful processing
            logger.info(f"Successfully processed file {file_info.path}")
            logger.info("Processing details:")
            logger.info(f"  - File path: {file_info.path}")
            logger.info(f"  - Embedding dimensions: {len(embeddings)}")
            logger.info(f"  - Processing time: {datetime.utcnow().isoformat()}")

        except Exception as e:
            logger.error(f"Error processing file {file_info.path}: {str(e)}")
            raise

    def process_manifest(self, record: Dict) -> None:
        try:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            logger.info(f"Processing manifest from bucket: {bucket}, key: {key}")
            
            if not key.startswith('manifests/') or not key.endswith('.json'):
                logger.info(f"Skipping non-manifest file: {key}")
                return
            
            response = self.s3_client.get_object(
                Bucket=self.processing_bucket,
                Key=key
            )
            manifest_content = response['Body'].read().decode('utf-8')
            
            manifest_data = ManifestData.from_json(json.loads(manifest_content))
            logger.info(f"Processing commit: {manifest_data.commit_info.sha}")
            logger.info(f"Repository: {manifest_data.repository.url}")
            logger.info(f"Total files to process: {len(manifest_data.files)}")
            
            processed_files = 0
            for file_info in manifest_data.files:
                try:
                    response = self.s3_client.get_object(
                        Bucket=self.processing_bucket,
                        Key=file_info.s3_key
                    )
                    file_content = response['Body'].read().decode('utf-8')
                    
                    self.process_file(file_content, file_info)
                    processed_files += 1
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_info.path}: {str(e)}")
                    continue
            
            logger.info(f"Manifest processing complete:")
            logger.info(f"  - Successfully processed: {processed_files}/{len(manifest_data.files)} files")
            logger.info(f"  - Commit SHA: {manifest_data.commit_info.sha}")
            logger.info(f"  - Processing time: {datetime.utcnow().isoformat()}")
            
        except Exception as e:
            logger.error(f"Error processing manifest: {str(e)}")
            raise

def handler(event: Dict, context: Any) -> Dict[str, Any]:
    logger.info("Starting analysis processor")
    logger.info(f"Event: {json.dumps(event)}")
    
    processor = AnalysisProcessor()
    
    try:
        records_processed = 0
        for record in event.get('Records', []):
            processor.process_manifest(record)
            records_processed += 1
        
        logger.info(f"Processing complete. Processed {records_processed} records")
        return {
            'statusCode': 200,
            'body': f'Successfully processed {records_processed} records'
        }
    except Exception as e:
        logger.error(f"Handler failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Processing failed: {str(e)}"
        }
    
    