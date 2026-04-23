#!/usr/bin/env python3
"""Test script to verify Gmail IMAP connection"""
import asyncio
import sys
from app.core.config import get_settings

async def test_gmail_connection():
    """Test IMAP connection to Gmail"""
    settings = get_settings()

    print(f"Testing Gmail connection...")
    print(f"Host: {settings.imap_host}")
    print(f"Port: {settings.imap_port}")
    print(f"Username: {settings.imap_username}")
    print(f"Use SSL: {settings.imap_use_ssl}")
    print()

    try:
        from app.infrastructure.email.imap_client import IMAPClient

        imap_client = IMAPClient(
            host=settings.imap_host,
            port=settings.imap_port,
            username=settings.imap_username,
            password=settings.imap_password,
            use_ssl=settings.imap_use_ssl,
        )

        print("✓ IMAP Client created successfully")

        # Try to connect
        result = await imap_client.connect()
        print(f"✓ Connected to Gmail: {result}")

        # List mailboxes
        mailboxes = await imap_client.list_mailboxes()
        print(f"✓ Found {len(mailboxes)} mailboxes:")
        for mb in mailboxes[:5]:  # Show first 5
            print(f"  - {mb}")

        # Close connection
        await imap_client.close()
        print("✓ Connection closed successfully")

        print("\n✅ Gmail connection test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Gmail connection test FAILED!")
        print(f"Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_gmail_connection())
    sys.exit(0 if success else 1)
