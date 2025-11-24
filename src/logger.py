import logging
import os
import sys
from datetime import datetime
import json


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging similar to pino."""

    def format(self, record):
        log_data = {
            'level': record.levelname.lower(),
            'time': datetime.utcnow().isoformat() + 'Z',
            'service': 'communication-agent',
            'msg': record.getMessage()
        }

        # Add exception info if present
        if record.exc_info:
            log_data['err'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'stack': self.formatException(record.exc_info)
            }

        # Add extra fields from the record
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


# Configure the logger
logger = logging.getLogger('communication-agent')
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())

# Create console handler with JSON formatter
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)

# Prevent propagation to root logger
logger.propagate = False


def log_with_context(level, msg, **context):
    """Helper function to log with additional context fields."""
    extra = {'extra_data': context} if context else {}
    logger.log(level, msg, extra=extra)


# Convenience methods
def info(msg, **context):
    log_with_context(logging.INFO, msg, **context)


def error(msg, err=None, **context):
    if err:
        context['err'] = {'message': str(err), 'type': type(err).__name__}
    log_with_context(logging.ERROR, msg, **context)


def warn(msg, **context):
    log_with_context(logging.WARNING, msg, **context)


def debug(msg, **context):
    log_with_context(logging.DEBUG, msg, **context)
