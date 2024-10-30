from typing import Optional
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from ..database.models import GitAccount

class GitHubClient:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.session = aiohttp.ClientSession()

    async def get_file_content(
        self,
        session: AsyncSession,
        git_account_id: str,
        repo_url: str,
        file_path: str,
        ref: str
    ) -> str:
        try:
            # Get access token from database
            account = await session.get(GitAccount, git_account_id)
            if not account or not account.access_token:
                raise ValueError(f"No valid access token for account {git_account_id}")

            # Parse repo owner and name from URL
            _, _, owner, repo = repo_url.rstrip('/').rsplit('/', 3)

            headers = {
                "Authorization": f"Bearer {account.access_token}",
                "Accept": "application/vnd.github.v3.raw"
            }

            async with self.session.get(
                f"{self.base_url}/repos/{owner}/{repo}/contents/{file_path}",
                headers=headers,
                params={"ref": ref}
            ) as response:
                response.raise_for_status()
                return await response.text()

        except aiohttp.ClientError as e:
            raise RuntimeError(f"GitHub API error: {str(e)}")

    async def close(self):
        await self.session.close()