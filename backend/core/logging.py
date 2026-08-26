import json
import logging
import threading

# Standard attributes every LogRecord carries. Anything else on the record
# came from an explicit `extra={...}` call and is structured data we want in
# the output (actor_id, ip, action, outcome, etc. — see core/audit.py).
_STANDARD_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JSONFormatter(logging.Formatter):
    """Emits one JSON object per line to stdout (ASVS 16.2.1/16.2.2).

    Using `json.dumps` for the whole record — rather than string-formatting
    fields into a template — is what satisfies 16.4.1 (encode log data to
    prevent log injection): any newline or control character an attacker
    puts in, say, an email address is JSON-escaped inside a string value, so
    it can never inject a fake extra log line into the stream.
    """

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in payload:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_fixed_azure_log_handler_class = None


def _get_fixed_azure_log_handler_class():
    """`opencensus_ext_azure.log_exporter.AzureLogHandler` (confirmed on
    1.1.15) overrides `createLock()` to set `self.lock = None` but never
    overrides `handle()`, so the inherited `logging.Handler.handle()`'s
    `with self.lock:` crashes on every single log call — reproduced by hand
    before wiring this in. This subclass restores a real lock; everything
    else (batching, retry, local-storage fallback) is unmodified upstream
    behavior. Imported lazily so this module never requires
    `opencensus-ext-azure` to be installed unless it's actually used."""
    global _fixed_azure_log_handler_class
    if _fixed_azure_log_handler_class is None:
        from opencensus.ext.azure.log_exporter import AzureLogHandler as _RealAzureLogHandler

        class FixedAzureLogHandler(_RealAzureLogHandler):
            def createLock(self):
                self.lock = threading.RLock()

        _fixed_azure_log_handler_class = FixedAzureLogHandler
    return _fixed_azure_log_handler_class


class AzureLogHandler:
    """Proxy class referenced by settings.LOGGING's class path
    ("core.logging.AzureLogHandler") — logging.config.dictConfig calls this
    like a constructor; `__new__` returns an instance of the real, patched
    handler instead (see `_get_fixed_azure_log_handler_class`), so
    `opencensus-ext-azure` is only imported when this class is actually
    instantiated (i.e. when AZURE_LOG_ANALYTICS_CONNECTION_STRING is set)."""

    def __new__(cls, *args, **kwargs):
        handler_class = _get_fixed_azure_log_handler_class()
        return handler_class(*args, **kwargs)
