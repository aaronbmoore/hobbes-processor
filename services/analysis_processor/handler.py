import os
import sys
import json
import logging
import boto3
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from openai import OpenAI
from code_analysis import CodeAnalyzer
# from qdrant_manager import QdrantManager
from qdrant_http_client import QdrantHttpClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

logging.info(f"Python sys.path at startup: {sys.path}")

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
        self._claude_api_key: Optional[str] = None
        self._qdrant_api_key: Optional[str] = None

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
    
    def get_claude_api_key(self) -> str:
        if not self._claude_api_key:
            try:
                param_name = os.environ['CLAUDE_API_KEY_PARAM']
                response = self.ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                self._claude_api_key = response['Parameter']['Value']
            except Exception as e:
                logger.error(f"Failed to get Claude API key: {str(e)}")
                raise
        return self._claude_api_key
    
    def get_qdrant_api_key(self) -> str:
        if not self._qdrant_api_key:
            try:
                param_name = os.environ['QDRANT_API_KEY_PARAM']
                response = self.ssm_client.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                self._qdrant_api_key = response['Parameter']['Value']
            except Exception as e:
                logger.error(f"Failed to get Qdrant API key: {str(e)}")
                raise
        return self._qdrant_api_key

class AnalysisProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.processing_bucket = os.environ['PROCESSING_BUCKET']
        self.api_key_manager = APIKeyManager()
        self.openai_client = None
        self.code_analyzer = None
        # self.qdrant_manager = None
        self.qdrant_client = None

        logger.info(f"Initialized AnalysisProcessor with bucket: {self.processing_bucket}")

    def init_openai(self):
        """Initialize OpenAI client with API key"""
        try:
            if not self.openai_client:
                api_key = self.api_key_manager.get_openai_api_key()
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("Successfully initialized OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise    

    def init_code_analyzer(self):
        """Initialize the code analyzer with Claude API key"""
        if not self.code_analyzer:
            api_key = self.api_key_manager.get_claude_api_key()
            self.code_analyzer = CodeAnalyzer(api_key=api_key)
            logger.info("Successfully initialized Code Analyzer")

    # use this with qdrant manager code, but not working with lambda
    # def init_qdrant(self):
    #     """Initialize Qdrant client if needed"""
    #     if not self.qdrant_manager:
    #         api_key = self.api_key_manager.get_qdrant_api_key()
    #         self.qdrant_manager = QdrantManager(api_key)
    #         # Ensure collection exists
    #         self.qdrant_manager.ensure_collection()
    #         logger.info("Successfully initialized Qdrant manager")


    def init_qdrant(self):
        """Initialize Qdrant client if needed"""
        if not self.qdrant_client:
            api_key = self.api_key_manager.get_qdrant_api_key()
            self.qdrant_client = QdrantHttpClient(api_key=api_key)
            # Ensure collection exists
            self.qdrant_client.ensure_collection()
            logger.info("Successfully initialized Qdrant client")


    def generate_segment_id(self, repository_id: str, file_path: str, content: str) -> str:
        """Generate a unique segment ID based on repository, file path, and content"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"{repository_id}:{file_path}:{content_hash}"

    def create_base_metadata(self, 
                           file_content: str,
                           file_info: FileInfo, 
                           manifest_data: ManifestData,
                           embeddings: List[float]) -> Dict:
        """Create comprehensive metadata structure"""
        try:
            segment_id = self.generate_segment_id(
                manifest_data.repository.id,
                file_info.path,
                file_content
            )

            # Initialize code analyzer if needed
            self.init_code_analyzer()

            # Get code analysis
            code_analysis = self.code_analyzer.analyze_code(
                file_info.path,
                file_content,
                manifest_data.repository.url
            )

            metadata = {
                "id": segment_id,
                "vector": embeddings,
                "payload": {
                    "segment_info": {
                        "segment_id": segment_id,
                        "file_path": file_info.path,
                        "content_hash": file_info.sha,
                        "content_length": len(file_content),
                        "created_at": datetime.utcnow().isoformat()
                    },
                    "file_context": {
                        "repository_id": manifest_data.repository.id,
                        "project_id": manifest_data.repository.project_id,
                        "path": file_info.path,
                        "git_sha": file_info.sha,
                        "previous_git_sha": file_info.previous_sha
                    },
                    "git_context": {
                        "repository_url": manifest_data.repository.url,
                        "branch": manifest_data.repository.branch,
                        "commit_info": {
                            "sha": manifest_data.commit_info.sha,
                            "message": manifest_data.commit_info.message,
                            "author": manifest_data.commit_info.author,
                            "timestamp": manifest_data.commit_info.timestamp
                        }
                    },
                    "code_analysis": code_analysis.get('code_analysis', {}),
                    "context": code_analysis.get('context', {}),
                    "filters": code_analysis.get('search_filters', {})
                }
            }

            return metadata
        except Exception as e:
            logger.error(f"Error creating metadata: {str(e)}")
            raise

    def get_embeddings(self, text: str) -> list[float]:
        """Generate embeddings for text using OpenAI API"""
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

    def process_file(self, file_content: str, file_info: FileInfo, manifest_data: ManifestData) -> None:
        """Process a single file and generate embeddings with metadata"""
        try:
            logger.info(f"Processing file: {file_info.path}")
            logger.info(f"Content length: {len(file_content)}")
            
            # Generate embeddings
            embeddings = self.get_embeddings(file_content)
            
            # Create metadata structure
            metadata = self.create_base_metadata(
                file_content,
                file_info,
                manifest_data,
                embeddings
            )

            # Initialize Qdrant if needed
            self.init_qdrant()
            
            # # Store in Qdrant this is for QDrant manager code
            # self.qdrant_manager.store_vector(
            #     id=metadata['id'],
            #     vector=metadata['vector'],
            #     payload=metadata['payload']
            # )     

            # Store in Qdrant
            self.qdrant_client.store_vector(
                id=metadata['id'],
                vector=metadata['vector'],
                payload=metadata['payload']
            )       
            
            # Log the complete metadata structure
            # logger.info("Generated metadata structure:")
            # logger.info(json.dumps(metadata, indent=2))
            
            # Log processing success
            logger.info(f"Successfully processed file {file_info.path}")
            logger.info(f"Segment ID: {metadata['id']}")

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
                    
                    self.process_file(file_content, file_info, manifest_data)
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