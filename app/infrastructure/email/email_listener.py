import asyncio
import logging
from typing import Optional
from email import message_from_bytes
from email.header import decode_header, make_header
from app.infrastructure.email.imap_client import IMAPClient
from app.infrastructure.parsers.zip_extractor import extract_zip_contents
from app.infrastructure.parsers.link_extractor import extract_scored_links
from app.infrastructure.email.invoice_link_downloader import download_invoices_from_links

logger = logging.getLogger(__name__)


class EmailListener:
    """Listen for new emails and process them using IMAP IDLE"""

    def __init__(self, imap_client: IMAPClient, process_use_case, poll_interval: int = 600):
        self.imap_client = imap_client
        self.process_use_case = process_use_case
        self.poll_interval = poll_interval  # Used as IDLE timeout (max 29 min for Gmail)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _decode_filename(filename: str) -> str:
        try:
            return str(make_header(decode_header(filename)))
        except Exception:
            return filename

    def _extract_attachments_from_raw(self, raw_bytes: bytes):
        """Extract attachments from raw email bytes"""
        attachments = []
        try:
            msg = message_from_bytes(raw_bytes)
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_filename(filename)
                        file_data = part.get_payload(decode=True)
                        attachments.append({
                            "filename": filename,
                            "data": file_data,
                        })
                        logger.debug(f"[EmailListener] Extracted attachment: {filename} ({len(file_data)} bytes)")
        except Exception as e:
            logger.error(f"[EmailListener] Error extracting attachments: {e}")
        return attachments

    def _extract_body_from_raw(self, raw_bytes: bytes) -> str:
        """Extract HTML body from raw email bytes"""
        try:
            msg = message_from_bytes(raw_bytes)
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="ignore")
        except Exception as e:
            logger.error(f"[EmailListener] Error extracting body: {e}")
        return ""

    async def _process_emails(self):
        """Process new emails - called when IDLE detects new emails"""
        try:
            logger.debug(f"[EmailListener] Checking for unseen emails")
            emails = await self.imap_client.fetch_new_emails()

            if not emails:
                logger.debug(f"[EmailListener] No unseen emails")
                return

            logger.info(f"[EmailListener] Found {len(emails)} new emails to process")

            processed_count = 0
            for idx, email in enumerate(emails, 1):
                logger.info(f"[EmailListener] Email {idx}/{len(emails)} - From: {email['from']}, Subject: {email['subject']}")
                logger.debug(f"[EmailListener] Email ID: {email['id']}, Date: {email['date']}")

                # Extract attachments from the raw bytes already fetched
                raw = email.get("raw")
                if not raw:
                    logger.warning(f"[EmailListener] No raw data for email {email['id']}")
                    continue

                attachments = self._extract_attachments_from_raw(raw)

                if not attachments:
                    logger.info(f"[EmailListener] No attachments found in email {email['id']}, checking for download links...")
                    body = self._extract_body_from_raw(raw)
                    links = extract_scored_links(body)
                    if links:
                        logger.info(f"[EmailListener] Found {len(links)} potential invoice links in email {email['id']}")
                        downloaded = await download_invoices_from_links(links)
                        if downloaded:
                            attachments = [
                                {"filename": fname, "data": fdata}
                                for fname, fdata in downloaded
                            ]
                            logger.info(f"[EmailListener] Successfully downloaded {len(attachments)} files from links")

                if not attachments:
                    logger.warning(f"[EmailListener] No attachments or valid download links found in email {email['id']}")
                    continue

                # Expand ZIP attachments before XML/PDF split
                expanded = []
                for a in attachments:
                    if a['filename'].lower().endswith('.zip'):
                        extracted = extract_zip_contents(a['filename'], a['data'])
                        logger.info(f"[EmailListener] ZIP {a['filename']} → {len(extracted)} files extracted")
                        expanded.extend(extracted)
                    else:
                        expanded.append(a)
                attachments = expanded

                if not attachments:
                    logger.warning(f"[EmailListener] No processable files in email {email['id']} after ZIP expansion")
                    continue

                # Split attachments by type. If the email has XML, only XML gets a job —
                # any PDF is attached as paired_pdf so it still gets uploaded to RustFS
                # on confirmation without creating a duplicate job.
                xmls = [a for a in attachments if a['filename'].lower().endswith(".xml")]
                pdfs = [a for a in attachments if a['filename'].lower().endswith(".pdf")]
                others = [
                    a for a in attachments
                    if not a['filename'].lower().endswith((".xml", ".pdf"))
                ]

                tasks: list[tuple[dict, dict | None]] = []  # (primary, paired_pdf_attachment)

                if xmls:
                    # Match each XML to a PDF by base filename; fall back to positional pairing.
                    used_pdf_ids: set[int] = set()
                    for xml in xmls:
                        xml_base = xml['filename'].rsplit(".", 1)[0].lower()
                        match = next(
                            (
                                p for p in pdfs
                                if id(p) not in used_pdf_ids
                                and p['filename'].rsplit(".", 1)[0].lower() == xml_base
                            ),
                            None,
                        )
                        if match is None:
                            match = next(
                                (p for p in pdfs if id(p) not in used_pdf_ids),
                                None,
                            )
                        if match is not None:
                            used_pdf_ids.add(id(match))
                            logger.info(f"[EmailListener] Pairing PDF {match['filename']} with XML {xml['filename']} (no separate job for the PDF)")
                        tasks.append((xml, match))

                    for p in pdfs:
                        if id(p) not in used_pdf_ids:
                            logger.info(f"[EmailListener] Skipping extra PDF without matching XML pair: {p['filename']}")
                else:
                    # No XML — each PDF gets its own job.
                    for p in pdfs:
                        tasks.append((p, None))

                for o in others:
                    tasks.append((o, None))

                for primary, paired in tasks:
                    filename = primary['filename']
                    file_data = primary['data']
                    paired_bytes = paired['data'] if paired else None

                    logger.info(f"[EmailListener] Processing attachment: {filename} ({len(file_data)} bytes){' + paired PDF' if paired_bytes else ''}")

                    try:
                        job = await self.process_use_case.execute(
                            filename=filename,
                            file_data=file_data,
                            paired_pdf=paired_bytes,
                        )
                        logger.info(f"[EmailListener] Successfully created job {job.id} from {filename} (Status: {job.status})")
                        processed_count += 1

                    except Exception as e:
                        logger.error(f"[EmailListener] Failed to process {filename}: {type(e).__name__}: {e}")
                        logger.debug(f"[EmailListener] Error details:", exc_info=True)

            logger.info(f"[EmailListener] Processed {processed_count} attachments from {len(emails)} emails")

        except Exception as e:
            logger.error(f"[EmailListener] Error processing emails: {type(e).__name__}: {e}")
            logger.debug(f"[EmailListener] Error details:", exc_info=True)

    async def start(self):
        """Start listening for new emails using IMAP IDLE (real-time)"""
        self._running = True

        # Gmail IDLE timeout is ~29 min; cap at 600s (10 min) for safety
        idle_timeout = min(self.poll_interval, 600)

        logger.info(f"[EmailListener] Email listener started (IMAP IDLE with {idle_timeout}s refresh)")

        try:
            logger.debug(f"[EmailListener] Connecting to IMAP server")
            await self.imap_client.connect()
            logger.info(f"[EmailListener] Connected to IMAP server, starting IDLE listener")

            # Use IDLE mode for real-time email detection
            await self.imap_client.idle_listen(
                callback=self._process_emails,
                idle_timeout=idle_timeout,
            )

        except asyncio.CancelledError:
            logger.info(f"[EmailListener] Listener cancelled")
        except Exception as e:
            logger.error(f"[EmailListener] Error in listener: {type(e).__name__}: {e}")
            logger.debug(f"[EmailListener] Error details:", exc_info=True)
        finally:
            try:
                logger.debug(f"[EmailListener] Closing IMAP connection")
                await self.imap_client.close()
                logger.info(f"[EmailListener] IMAP connection closed")
            except Exception as e:
                logger.warning(f"[EmailListener] Error closing connection: {e}")

            logger.info(f"[EmailListener] Email listener stopped")

    def stop(self):
        """Stop listening for emails"""
        self._running = False
        logger.info("[EmailListener] Stopping email listener...")
