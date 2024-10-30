import os
import json
import logging
import boto3
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_async_session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
s3_client = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

class AnalysisProcessor:
    def __init__(self):
        self.processing_bucket = os.environ['PROCESSING_BUCKET']
        self.service_name = os.environ.get('POWERTOOLS_SERVICE_NAME', 'analysis-processor')

    async def emit_metric(self, metric_name: str, value: float = 1, unit: str = 'Count', dimensions: Optional[List[Dict]] = None):
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

    async def process_manifest(self, manifest_key: str, db_session: AsyncSession) -> None:
        processing_start = datetime.utcnow()
        
        try:
            # Get manifest from S3
            manifest_response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: s3_client.get_object(
                    Bucket=self.processing_bucket,
                    Key=manifest_key
                )
            )
            
            manifest = json.loads(manifest_response['Body'].read().decode('utf-8'))
            
            # Process files from manifest
            for file_info in manifest['files']:
                try:
                    # Get file content from S3
                    content_response = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: s3_client.get_object(
                            Bucket=self.processing_bucket,
                            Key=file_info['s3_key']
                        )
                    )
                    
                    content = content_response['Body'].read().decode('utf-8')
                    
                    # TODO: Implement analysis logic here
                    # - Generate metadata
                    # - Create vectors
                    # - Store in Qdrant
                    
                    await self.emit_metric('FilesAnalyzed')
                    
                except Exception as e:
                    await self.emit_metric('FileAnalysisErrors')
                    logger.error(f"Error analyzing file {file_info['path']}: {str(e)}")
                    continue
            
            # Update manifest status
            manifest['status'] = 'analyzed'
            manifest['analyzed_at'] = datetime.utcnow().isoformat()
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: s3_client.put_object(
                    Bucket=self.processing_bucket,
                    Key=manifest_key,
                    Body=json.dumps(manifest).encode('utf-8')
                )
            )
            
            # Emit processing duration metric
            processing_duration = (datetime.utcnow() - processing_start).total_seconds()
            await self.emit_metric('AnalysisDuration', value=processing_duration, unit='Seconds')
            await self.emit_metric('ManifestsProcessed')
            
        except Exception as e:
            await self.emit_metric('ManifestProcessingErrors')
            logger.error(f"Error processing manifest {manifest_key}: {str(e)}")
            raise

async def handler(event: Dict, context: Any) -> Dict:
    processor = AnalysisProcessor()
    
    async with get_async_session() as session:
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            if key.startswith('manifests/') and key.endswith('.json'):
                await processor.process_manifest(key, session)
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Analysis complete'})
    }

def lambda_handler(event: Dict, context: Any) -> Dict:
    return asyncio.run(handler(event, context))