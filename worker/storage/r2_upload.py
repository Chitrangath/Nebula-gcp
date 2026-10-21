"""Result upload to Cloudflare R2."""

import logging
import pickle

logger = logging.getLogger(__name__)


async def upload_result(job_id: str, result, session, settings) -> str:
    """Upload result to R2 and pin to IPFS. Returns IPFS hash."""
    # 1. Get presigned upload URL from backend
    async with session.post(
        f"{settings.BACKEND_URL}/v1/jobs/{job_id}/result-url",
        headers={"Authorization": f"Bearer {settings.API_KEY}"},
    ) as resp:
        data = await resp.json()
        upload_url = data["upload_url"]
        ipfs_hash = data["ipfs_hash"]

    # 2. Upload to R2
    result_bytes = pickle.dumps(result)
    async with session.put(upload_url, data=result_bytes) as resp:
        resp.raise_for_status()

    return ipfs_hash
