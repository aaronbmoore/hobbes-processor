import os
from qdrant_client import QdrantClient
from qdrant_client.http import models
import logging

logger = logging.getLogger()

class QdrantManager:
    def __init__(self, api_key: str):
        self.client = QdrantClient(
            url="https://cff8839c-06e9-4ec5-82f5-f0713e927e07.us-east4-0.gcp.cloud.qdrant.io",
            api_key=api_key
        )
        self.collection_name = "code_segments"

    def ensure_collection(self):
        """Create collection if it doesn't exist"""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=1536,  # OpenAI ada-002 dimension
                        distance=models.Distance.COSINE
                    )
                )
                
                # Create payload indexes for efficient filtering
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="payload.file_context.language",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="payload.file_context.type",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="payload.filters.pattern_types",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                
                logger.info("Collection and indexes created successfully")
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Error ensuring collection: {str(e)}")
            raise

    def store_vector(self, id: str, vector: list[float], payload: dict):
        """Store a vector with its metadata"""
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=id,
                        vector=vector,
                        payload=payload
                    )
                ]
            )
            logger.info(f"Successfully stored vector for id: {id}")
        except Exception as e:
            logger.error(f"Error storing vector: {str(e)}")
            raise