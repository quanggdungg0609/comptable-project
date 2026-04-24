import pytest
from app.infrastructure.notifications.console_notifier import ConsoleNotifier


@pytest.mark.asyncio
async def test_notify_new_invoice_logs(caplog):
    import logging
    notifier = ConsoleNotifier()
    with caplog.at_level(logging.INFO):
        await notifier.notify_new_invoice("job-1", "hd001.xml", "Cty ABC", "0001")
    assert "hd001.xml" in caplog.text


@pytest.mark.asyncio
async def test_notify_confirmed_logs(caplog):
    import logging
    notifier = ConsoleNotifier()
    with caplog.at_level(logging.INFO):
        await notifier.notify_confirmed("job-1", "hd001.xml", "Cty ABC", "0001")
    assert "hd001.xml" in caplog.text


@pytest.mark.asyncio
async def test_notify_rejected_logs(caplog):
    import logging
    notifier = ConsoleNotifier()
    with caplog.at_level(logging.INFO):
        await notifier.notify_rejected("job-1", "hd001.xml", "Cty ABC", "0001")
    assert "hd001.xml" in caplog.text
