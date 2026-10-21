"""IPFS pinning via backend (Pinata)."""


async def pin_to_ipfs(job_id: str, session, settings) -> str:
    """Pin result to IPFS via backend endpoint."""
    # Backend handles Pinata integration
    # Worker just calls the endpoint
    pass
