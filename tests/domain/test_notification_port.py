from app.domain.ports.notification_port import INotificationPort
import inspect


def test_notification_port_has_required_methods():
    methods = {name for name, _ in inspect.getmembers(INotificationPort, predicate=inspect.isfunction)}
    assert "notify_new_invoice" in methods
    assert "notify_confirmed" in methods
    assert "notify_rejected" in methods


def test_notify_new_invoice_signature():
    sig = inspect.signature(INotificationPort.notify_new_invoice)
    params = list(sig.parameters.keys())
    assert params == ["self", "job_id", "filename", "seller_name", "invoice_number"]


def test_notify_confirmed_signature():
    sig = inspect.signature(INotificationPort.notify_confirmed)
    params = list(sig.parameters.keys())
    assert params == ["self", "job_id", "filename", "seller_name", "invoice_number"]


def test_notify_rejected_signature():
    sig = inspect.signature(INotificationPort.notify_rejected)
    params = list(sig.parameters.keys())
    assert params == ["self", "job_id", "filename", "seller_name", "invoice_number"]
