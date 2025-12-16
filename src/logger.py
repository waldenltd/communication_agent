import logging
import os
import sys
from datetime import datetime
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path


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


# Ensure logs directory exists
logs_dir = Path(__file__).parent.parent / 'logs'
logs_dir.mkdir(exist_ok=True)
log_file_path = logs_dir / 'app.log'

# Configure the logger
logger = logging.getLogger('communication-agent')
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())

# Create console handler with JSON formatter
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(JSONFormatter())
logger.addHandler(console_handler)

# Create file handler with rotation (10MB max, keep 5 backups)
file_handler = RotatingFileHandler(
    log_file_path,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(JSONFormatter())
logger.addHandler(file_handler)

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
