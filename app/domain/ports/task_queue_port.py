from abc import ABC, abstractmethod

class ITaskQueue(ABC):
    @abstractmethod
    async def enqueue(self, filename: str, file_data: bytes, paired_pdf: bytes | None = None) -> str:
        """
        Enqueue a job for processing. Returns the job_id.
        """
        pass

    @abstractmethod
    async def start_workers(self, num_workers: int = 2):
        """
        Start the background worker loop.
        """
        pass

    @abstractmethod
    async def stop_workers(self):
        """
        Stop the background worker loop.
        """
        pass
