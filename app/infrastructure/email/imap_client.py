import asyncio
import logging
from email import message_from_bytes
from typing import List, Callable
from imapclient import IMAPClient as _IMAPClient
from imapclient.exceptions import IMAPClientError

logger = logging.getLogger(__name__)


class IMAPClient:
    """IMAP client for connecting to email servers like Gmail using IDLE"""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.imap = None

    async def connect(self) -> bool:
        """Connect to IMAP server"""
        try:
            loop = asyncio.get_event_loop()

            logger.debug(f"[IMAPClient] Connecting to {self.host}:{self.port} (SSL: {self.use_ssl})")

            def _connect():
                client = _IMAPClient(self.host, port=self.port, ssl=self.use_ssl)
                client.login(self.username, self.password)
                return client

            self.imap = await loop.run_in_executor(None, _connect)

            logger.info(f"[IMAPClient] Successfully connected and authenticated to {self.host}:{self.port} as {self.username}")
            return True
        except Exception as e:
            logger.error(f"[IMAPClient] Failed to connect to IMAP ({self.host}:{self.port}): {type(e).__name__}: {e}")
            raise

    async def list_mailboxes(self) -> List[str]:
        """List available mailboxes"""
        try:
            if not self.imap:
                await self.connect()

            loop = asyncio.get_event_loop()
            folders = await loop.run_in_executor(None, lambda: self.imap.list_folders())

            mailbox_names = [folder[2] for folder in folders]
            logger.info(f"Found mailboxes: {mailbox_names}")
            return mailbox_names
        except Exception as e:
            logger.error(f"Failed to list mailboxes: {e}")
            return ["INBOX"]

    async def fetch_new_emails(
        self,
        mailbox: str = "INBOX",
        unseen_only: bool = True,
    ) -> List[dict]:
        """Fetch new emails from mailbox"""
        try:
            if not self.imap:
                logger.debug(f"[IMAPClient] No connection, reconnecting")
                await self.connect()

            loop = asyncio.get_event_loop()

            logger.debug(f"[IMAPClient] Selecting mailbox: {mailbox}")
            await loop.run_in_executor(None, lambda: self.imap.select_folder(mailbox))

            search_criteria = ["UNSEEN"] if unseen_only else ["ALL"]
            logger.debug(f"[IMAPClient] Searching for emails (criteria: {search_criteria})")

            email_ids = await loop.run_in_executor(
                None,
                lambda: self.imap.search(search_criteria),
            )

            logger.info(f"[IMAPClient] Found {len(email_ids)} {search_criteria[0]} emails in {mailbox}")

            if not email_ids:
                return []

            fetch_limit = 10
            ids_to_fetch = email_ids[-fetch_limit:] if len(email_ids) > fetch_limit else email_ids

            logger.debug(f"[IMAPClient] Fetching {len(ids_to_fetch)} emails (limit: {fetch_limit})")

            messages = await loop.run_in_executor(
                None,
                lambda: self.imap.fetch(ids_to_fetch, ["RFC822"]),
            )

            # Mark fetched emails as \Seen immediately so the next IDLE cycle
            # does not re-fetch and re-process the same messages.
            await loop.run_in_executor(
                None,
                lambda: self.imap.add_flags(ids_to_fetch, [b"\\Seen"]),
            )

            emails = []
            for email_id, data in messages.items():
                try:
                    raw = data.get(b"RFC822") or data.get("RFC822")
                    if not raw:
                        continue
                    msg = message_from_bytes(raw)
                    email_info = {
                        "id": email_id,
                        "from": msg.get("From", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""),
                        "raw": raw,
                    }
                    emails.append(email_info)
                    logger.debug(f"[IMAPClient] Parsed email {email_id} - From: {email_info['from'][:50]}, Subject: {email_info['subject'][:50]}")
                except Exception as e:
                    logger.error(f"[IMAPClient] Failed to parse email {email_id}: {e}")

            logger.info(f"[IMAPClient] Successfully fetched {len(emails)} emails from {mailbox}")
            return emails
        except Exception as e:
            logger.error(f"[IMAPClient] Failed to fetch emails from {mailbox}: {type(e).__name__}: {e}")
            logger.debug(f"[IMAPClient] Error details:", exc_info=True)
            return []

    async def idle_listen(self, callback: Callable, idle_timeout: int = 600):
        """Keep connection alive and listen for new emails using IMAP IDLE (real-time)"""
        loop = asyncio.get_event_loop()

        try:
            if not self.imap:
                await self.connect()

            logger.info(f"[IMAPClient] Starting IDLE mode (idle timeout: {idle_timeout}s)")

            # Select INBOX first
            await loop.run_in_executor(None, lambda: self.imap.select_folder("INBOX"))
            logger.info(f"[IMAPClient] INBOX selected, entering IDLE mode")

            # Process any existing unseen emails on startup
            await callback()

            while True:
                try:
                    # Enter IDLE mode
                    logger.debug(f"[IMAPClient] Entering IDLE state")
                    await loop.run_in_executor(None, lambda: self.imap.idle())

                    # Wait for push notification from server
                    logger.debug(f"[IMAPClient] Waiting for server push (timeout: {idle_timeout}s)")
                    responses = await loop.run_in_executor(
                        None,
                        lambda: self.imap.idle_check(timeout=idle_timeout),
                    )

                    # End IDLE mode to run commands
                    await loop.run_in_executor(None, lambda: self.imap.idle_done())

                    if responses:
                        logger.info(f"[IMAPClient] IDLE push received: {responses}")
                        # Check if there's an EXISTS response (new email)
                        has_new = any(
                            (isinstance(r, tuple) and len(r) >= 2 and r[1] in (b"EXISTS", "EXISTS"))
                            for r in responses
                        )
                        if has_new:
                            logger.info(f"[IMAPClient] New email detected, triggering callback")
                            await callback()
                        else:
                            logger.debug(f"[IMAPClient] No EXISTS in response, checking anyway")
                            await callback()
                    else:
                        # Timeout — periodic check to keep connection alive
                        logger.debug(f"[IMAPClient] IDLE timeout, doing periodic check")
                        await callback()

                except (IMAPClientError, OSError, ConnectionError) as e:
                    logger.warning(f"[IMAPClient] Connection error in IDLE: {type(e).__name__}: {e}, reconnecting")
                    try:
                        await loop.run_in_executor(None, lambda: self.imap.logout())
                    except Exception:
                        pass
                    self.imap = None
                    await asyncio.sleep(5)
                    await self.connect()
                    await loop.run_in_executor(None, lambda: self.imap.select_folder("INBOX"))
                    logger.info(f"[IMAPClient] Reconnected and INBOX selected")

                except asyncio.CancelledError:
                    logger.info(f"[IMAPClient] IDLE cancelled")
                    try:
                        await loop.run_in_executor(None, lambda: self.imap.idle_done())
                    except Exception:
                        pass
                    raise

                except Exception as e:
                    logger.error(f"[IMAPClient] Error in IDLE loop: {type(e).__name__}: {e}")
                    logger.debug(f"[IMAPClient] Error details:", exc_info=True)
                    await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"[IMAPClient] Fatal error in idle_listen: {type(e).__name__}: {e}")
            logger.debug(f"[IMAPClient] Error details:", exc_info=True)
            raise

    async def close(self):
        """Close IMAP connection"""
        try:
            if self.imap:
                loop = asyncio.get_event_loop()
                try:
                    await loop.run_in_executor(None, lambda: self.imap.idle_done())
                except Exception:
                    pass
                try:
                    await loop.run_in_executor(None, lambda: self.imap.logout())
                except Exception:
                    pass
                logger.info("[IMAPClient] IMAP connection closed")
                self.imap = None
        except Exception as e:
            logger.debug(f"[IMAPClient] Error closing IMAP connection: {e}")
