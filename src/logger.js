const pino = require('pino');
const fs = require('fs');
const path = require('path');

// Ensure logs directory exists
const logsDir = path.join(__dirname, '..', 'logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

const logFilePath = path.join(logsDir, 'app.log');

// Create a multi-stream logger that writes to both stdout and file
const streams = [
  { stream: process.stdout },
  { stream: fs.createWriteStream(logFilePath, { flags: 'a' }) }
];

const logger = pino(
  {
    level: process.env.LOG_LEVEL || 'info',
    base: {
      service: 'communication-agent'
    },
    timestamp: () => `,"time":"${new Date().toISOString()}"`
  },
  pino.multistream(streams)
);

module.exports = logger;
