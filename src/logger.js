const pino = require('pino');

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  base: {
    service: 'communication-agent'
  },
  timestamp: () => `,"time":"${new Date().toISOString()}"`
});

module.exports = logger;
