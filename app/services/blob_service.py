class MockBlobService:
    """Simulates Azure Blob Storage — no real SDK calls."""

    async def upload(self, job_id: str, filename: str, content: bytes) -> str:
        return f"mock://blob/contracts/{job_id}/{filename}"

    async def download(self, blob_url: str) -> bytes:
        return b"Mock contract content"
