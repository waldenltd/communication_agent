import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from ENV_FILE if specified, or .env.local, or .env
env_file = os.getenv('ENV_FILE')
if env_file:
    load_dotenv(Path(env_file))
else:
    # Try .env.local first, then fall back to .env
    env_local = Path(__file__).parent.parent / '.env.local'
    if env_local.exists():
        load_dotenv(env_local)
    else:
        load_dotenv()


def _number_from_env(key: str, fallback: int) -> int:
    """Extract integer from environment variable with fallback."""
    raw = os.getenv(key)
    if raw is None:
        return fallback

    try:
        return int(raw)
    except ValueError:
        return fallback


# Main configuration
CENTRAL_DB_URL = os.getenv(
    'CENTRAL_DB_URL',
    'postgres://dms_agent@localhost:5432/dms_communications'
)

POLL_INTERVAL_MS = _number_from_env('POLL_INTERVAL_MS', 5000)
MAX_CONCURRENT_JOBS = _number_from_env('MAX_CONCURRENT_JOBS', 5)
RETRY_DELAY_MINUTES = _number_from_env('RETRY_DELAY_MINUTES', 5)
MAX_RETRIES = _number_from_env('MAX_RETRIES', 3)

# Scheduler configuration
SCHEDULER_CONFIG = {
    'service_reminder_hour_utc': _number_from_env('SERVICE_REMINDER_HOUR_UTC', 14),
    'invoice_reminder_hour_utc': _number_from_env('INVOICE_REMINDER_HOUR_UTC', 13),
    'service_reminder_interval_ms': 24 * 60 * 60 * 1000,  # 24 hours
    'invoice_reminder_interval_ms': 24 * 60 * 60 * 1000,  # 24 hours
    'appointment_confirmation_interval_ms': _number_from_env(
        'APPOINTMENT_CONFIRMATION_INTERVAL_MS',
        60 * 60 * 1000  # 1 hour
    ),
    'queue_processor_interval_ms': _number_from_env(
        'QUEUE_PROCESSOR_INTERVAL_MS',
        30 * 1000  # 30 seconds
    )
}

# DeepSeek AI Configuration (OpenAI-compatible API)
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
