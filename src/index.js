const logger = require('./logger');
const JobProcessor = require('./jobs/jobProcessor');
const Scheduler = require('./scheduler');
const { shutdownTenantPools } = require('./db/tenantDataGateway');
const { shutdownPool } = require('./db/centralDb');

const jobProcessor = new JobProcessor();
const scheduler = new Scheduler();

logger.info('Starting Communication Agent worker');
jobProcessor.start();
scheduler.start();

const shutdown = async (signal) => {
  logger.info({ signal }, 'Shutting down communication agent');
  jobProcessor.stop();
  scheduler.stop();

  await shutdownTenantPools();
  await shutdownPool();
  process.exit(0);
};

['SIGINT', 'SIGTERM'].forEach((signal) => {
  process.on(signal, () => shutdown(signal));
});
