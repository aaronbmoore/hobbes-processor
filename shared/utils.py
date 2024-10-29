import os
import boto3
from functools import lru_cache

@lru_cache(maxsize=1)
def get_database_url() -> str:
    """
    Get database URL from SSM Parameter Store.
    Cached to avoid repeated SSM calls within the same Lambda invocation.
    """
    ssm = boto3.client('ssm')
    response = ssm.get_parameter(
        Name=f'/{os.environ["PROJECT_NAME"]}/database-url',
        WithDecryption=True
    )
    return response['Parameter']['Value']