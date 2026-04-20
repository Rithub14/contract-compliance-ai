class BlobService:
    """In-memory blob store. Replace with azure-storage-blob SDK for production."""

    _store: dict[str, bytes] = {}

    async def upload(self, job_id: str, filename: str, content: bytes) -> str:
        key = f"{job_id}/{filename}"
        self._store[key] = content
        return f"blob://contracts/{key}"

    async def download(self, blob_url: str) -> bytes:
        key = blob_url.replace("blob://contracts/", "")
        return self._store.get(key, b"")
