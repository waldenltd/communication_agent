import os
import signal
import sys
import time
from src import logger
from src.jobs.job_processor import JobProcessor
from src.scheduler import Scheduler
from src.db.tenant_data_gateway import shutdown_tenant_pools
from src.db.central_db import shutdown_pool
from src.health import start_health_server, stop_health_server


def main():
    """Main entry point for the Communication Agent."""
    # Check if Level 2 Agent mode is enabled
    agent_mode = os.getenv('AGENT_MODE', 'legacy').lower()

    # Health server port (0 to disable)
    health_port = int(os.getenv('HEALTH_PORT', '8080'))

    if agent_mode == 'level2':
        # Use the new Level 2 Agent orchestrator
        run_level2_agent(health_port)
    elif agent_mode == 'hybrid':
        # Run both legacy and Level 2 agent in parallel
        run_hybrid_mode(health_port)
    else:
        # Legacy mode - original job processor
        run_legacy_mode(health_port)


def run_legacy_mode(health_port: int = 8080):
    """Run the original job processor and scheduler."""
    job_processor = JobProcessor()
    scheduler = Scheduler()

    logger.info('Starting Communication Agent worker (legacy mode)')

    job_processor.start()
    scheduler.start()

    # Start health server with basic status
    if health_port > 0:
        def get_status():
            return {
                "mode": "legacy",
                "running": True,
                "job_processor": "active",
                "scheduler": "active",
            }
        start_health_server(port=health_port, status_provider=get_status)

    def shutdown(signum, frame):
        """Graceful shutdown handler."""
        logger.info('Shutting down communication agent', signal=signum)

        job_processor.stop()
        scheduler.stop()
        stop_health_server()

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


def run_level2_agent(health_port: int = 8080):
    """Run the Level 2 Agent orchestrator."""
    from src.agent import start_orchestrator, stop_orchestrator, get_orchestrator
    from src.agent.agent_scheduler import start_agent_scheduler, stop_agent_scheduler

    logger.info('Starting Communication Agent (Level 2 Agent mode)')

    start_orchestrator()
    start_agent_scheduler()
    orchestrator = get_orchestrator()

    # Start health server with agent status and metrics
    if health_port > 0:
        def get_status():
            status = orchestrator.get_status()
            status["mode"] = "level2"
            return status

        def get_metrics():
            return orchestrator.get_prometheus_metrics()

        start_health_server(
            port=health_port,
            status_provider=get_status,
            metrics_provider=get_metrics,
        )

    def shutdown(signum, frame):
        """Graceful shutdown handler."""
        logger.info('Shutting down Level 2 Agent', signal=signum)

        stop_agent_scheduler()
        stop_orchestrator()
        stop_health_server()

        shutdown_tenant_pools()
        shutdown_pool()

        # Log final stats
        status = orchestrator.get_status()
        logger.info('Agent shutdown complete',
                    cycles=status['cycles_completed'],
                    jobs_processed=status['jobs_processed'],
                    jobs_failed=status['jobs_failed'])

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


def run_hybrid_mode(health_port: int = 8080):
    """Run both legacy job processor and Level 2 Agent in parallel."""
    from src.agent import start_orchestrator, stop_orchestrator, get_orchestrator

    job_processor = JobProcessor()
    scheduler = Scheduler()

    logger.info('Starting Communication Agent (hybrid mode: legacy + Level 2)')

    # Start legacy components
    job_processor.start()
    scheduler.start()

    # Start Level 2 Agent
    start_orchestrator()
    orchestrator = get_orchestrator()

    # Start health server with combined status and metrics
    if health_port > 0:
        def get_status():
            agent_status = orchestrator.get_status()
            return {
                "mode": "hybrid",
                "legacy": {
                    "job_processor": "active",
                    "scheduler": "active",
                },
                "agent": agent_status,
            }

        def get_metrics():
            return orchestrator.get_prometheus_metrics()

        start_health_server(
            port=health_port,
            status_provider=get_status,
            metrics_provider=get_metrics,
        )

    def shutdown(signum, frame):
        """Graceful shutdown handler."""
        logger.info('Shutting down communication agent (hybrid)', signal=signum)

        # Stop all components
        job_processor.stop()
        scheduler.stop()
        stop_orchestrator()
        stop_health_server()

        shutdown_tenant_pools()
        shutdown_pool()

        # Log final stats
        status = orchestrator.get_status()
        logger.info('Hybrid shutdown complete',
                    agent_cycles=status['cycles_completed'],
                    agent_jobs_processed=status['jobs_processed'])

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
