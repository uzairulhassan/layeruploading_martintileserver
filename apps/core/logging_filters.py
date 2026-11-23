"""Attach request_id to log records when a request is in progress."""
from __future__ import annotations

import logging

from .request_id import get_current_request_id


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        if not getattr(record, "request_id", None):
            record.request_id = get_current_request_id() or "-"
        return True
