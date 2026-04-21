import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    def notify(self, message: str) -> None:
        logger.info("[Notification] %s", message)

    async def notify_async(self, message: str) -> None:
        self.notify(message)

    async def notify_new_invoice(self, job_id: str, filename: str) -> None:
        logger.info("[Notification] New invoice ready for review: %s (job %s)", filename, job_id)
