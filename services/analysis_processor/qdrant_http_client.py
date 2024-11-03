import requests
import logging
from typing import Dict, List, Any
import json

logger = logging.getLogger()

class QdrantHttpClient:
    def __init__(self, api_key: str):
        self.base_url = "https://cff8839c-06e9-4ec5-82f5-f0713e927e07.us-east4-0.gcp.cloud.qdrant.io"
        self.headers = {
            "Content-Type": "application/json",
            "api-key": api_key
        }
        self.collection_name = "code_segments"

        # Verify initialization
        logger.info(f"Initializing Qdrant client with URL: {self.base_url}")
        logger.info(f"API Key (first 4 chars): {api_key[:4]}***")

    # def ensure_collection(self) -> bool:
    #     """Create collection if it doesn't exist"""
    #     try:
    #         # Check if collection exists
    #         response = requests.get(
    #             f"{self.base_url}/collections/{self.collection_name}",
    #             headers=self.headers
    #         )

    #         if response.status_code == 404:
    #             # Create collection
    #             create_payload = {
    #                 "name": self.collection_name,
    #                 "vectors": {
    #                     "size": 1536,
    #                     "distance": "Cosine"
    #                 }
    #             }
    #             response = requests.put(
    #                 f"{self.base_url}/collections/{self.collection_name}",
    #                 headers=self.headers,
    #                 json=create_payload
    #             )
                
    #             if response.status_code == 200:
    #                 logger.info(f"Created collection: {self.collection_name}")
    #                 return True
    #             else:
    #                 logger.error(f"Failed to create collection: {response.text}")
    #                 return False

    #         return True

    #     except Exception as e:
    #         logger.error(f"Error ensuring collection: {str(e)}")
    #         raise

def store_vector(self, id: str, vector: List[float], payload: Dict[str, Any]) -> bool:
    """Store a vector with its metadata"""
    try:
        points_payload = {
            "points": [
                {
                    "id": id,
                    "vector": vector,
                    "payload": payload
                }
            ]
        }

        # Debug log the exact payload
        logger.info("Sending payload to Qdrant:")
        logger.info(f"Points payload structure: {json.dumps(points_payload, indent=2)}")
        
        url = f"{self.base_url}/collections/{self.collection_name}/points"
        logger.info(f"Sending request to URL: {url}")
        logger.info(f"Headers: {self.headers}")

        response = requests.put(
            url,
            headers=self.headers,
            json=points_payload
        )

        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response content: {response.text}")

        if response.status_code == 200:
            logger.info(f"Successfully stored vector for id: {id}")
            return True
        else:
            logger.error(f"Failed to store vector. Status: {response.status_code}, Response: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error storing vector: {str(e)}")
        raise