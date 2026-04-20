from abc import ABC, abstractmethod


class IStoragePort(ABC):

    @abstractmethod
    async def upload_file(self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str
    ) -> str:
        """Upload file to storage and return the URL"""


    @abstractmethod
    async def download_file(self,
        bucket: str,
        key: str
    ) -> bytes:
        """Download file from storage and return the content"""

    @abstractmethod
    async def get_presigned_url(self,
        bucket: str,
        key: str,
        expires_in: int =3600
    ) -> str:
        """Get presigned URL for file download"""
        