const { Pool } = require('pg');
const config = require('../config');
const logger = require('../logger');

const pool = new Pool({
  connectionString: config.centralDbUrl,
  max: 25,
  idleTimeoutMillis: 30_000
});

const withTransaction = async (callback) => {
  const client = await pool.connect();

  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
};

const shutdownPool = async () => {
  try {
    await pool.end();
  } catch (error) {
    logger.error({ err: error }, 'Failed to close central DB pool');
  }
};

module.exports = {
  pool,
  withTransaction,
  query: (text, params) => pool.query(text, params),
  shutdownPool
};
