#!/usr/bin/env python
"""
Service wrapper that ensures local lib packages are available.
"""
import sys
import os

# Add local lib directory to Python path FIRST
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(script_dir, 'lib')
sys.path.insert(0, lib_path)
sys.path.insert(0, script_dir)

# Set working directory
os.chdir(script_dir)

# Now we can import everything
import signal
import time
from src import logger
from src.jobs.job_processor import JobProcessor
from src.scheduler import Scheduler
from src.db.tenant_data_gateway import shutdown_tenant_pools
from src.db.central_db import shutdown_pool


def main():
    """Main entry point for the Communication Agent."""
    job_processor = JobProcessor()
    scheduler = Scheduler()

    logger.info('Starting Communication Agent worker')

    job_processor.start()
    scheduler.start()

    def shutdown(signum, frame):
        """Graceful shutdown handler."""
        logger.info('Shutting down communication agent', signal=signum)

        job_processor.stop()
        scheduler.stop()

        shutdown_tenant_pools()
        shutdown_pool()

        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(signal.SIGINT, None)


if __name__ == '__main__':
    main()
