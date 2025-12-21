const dayjs = require('dayjs');
const { withTransaction, query } = require('../db/centralDb');

const parseJobRow = (row) => ({
  id: row.id,
  tenant_id: row.tenant_id,
  job_type: row.job_type,
  payload:
    typeof row.payload === 'string' ? JSON.parse(row.payload) : row.payload,
  status: row.status,
  retry_count: row.retry_count || 0,
  last_error: row.last_error,
  created_at: row.created_at,
  process_after: row.process_after
});

const claimPendingJobs = async (limit) => {
  if (!limit) {
    return [];
  }

  return withTransaction(async (client) => {
    const selectQuery = `
      SELECT *
      FROM communication_jobs
      WHERE status = 'pending'
        AND (process_after IS NULL OR process_after <= NOW())
      ORDER BY created_at ASC
      FOR UPDATE SKIP LOCKED
      LIMIT $1
    `;

    const { rows } = await client.query(selectQuery, [limit]);

    if (!rows.length) {
      return [];
    }

    const ids = rows.map((row) => row.id);
    await client.query(
      `
      UPDATE communication_jobs
      SET status = 'processing'
      WHERE id = ANY($1::bigint[])
    `,
      [ids]
    );

    return rows.map(parseJobRow);
  });
};

const markJobComplete = async (jobId, note) => {
  await query(
    `
    UPDATE communication_jobs
    SET status = 'complete',
        last_error = $2
    WHERE id = $1
  `,
    [jobId, note || null]
  );
};

const rescheduleJob = async ({
  jobId,
  retryCount,
  processAfter,
  lastError,
  status = 'pending'
}) => {
  await query(
    `
    UPDATE communication_jobs
    SET status = $2,
        retry_count = $3,
        process_after = $4,
        last_error = $5
    WHERE id = $1
  `,
    [jobId, status, retryCount, processAfter, lastError]
  );
};

const markJobFailed = async (jobId, lastError, status = 'failed') => {
  await query(
    `
    UPDATE communication_jobs
    SET status = $2,
        last_error = $3
    WHERE id = $1
  `,
    [jobId, status, lastError]
  );
};

const jobExistsForReference = async (tenantId, jobType, reference) => {
  if (!reference) {
    return false;
  }

  const { rows } = await query(
    `
    SELECT 1
    FROM communication_jobs
    WHERE tenant_id = $1
      AND job_type = $2
      AND payload ->> 'source_reference' = $3
      AND status IN ('pending', 'processing', 'complete')
    LIMIT 1
  `,
    [tenantId, jobType, reference]
  );

  return Boolean(rows.length);
};

const insertJob = async ({
  tenantId,
  jobType,
  payload,
  processAfter,
  status = 'pending',
  sourceReference
}) => {
  const enrichedPayload = {
    ...payload
  };

  const reference = sourceReference || payload?.source_reference;
  if (reference) {
    enrichedPayload.source_reference = reference;
  }

  if (reference && (await jobExistsForReference(tenantId, jobType, reference))) {
    return null;
  }

  await query(
    `
    INSERT INTO communication_jobs
      (tenant_id, job_type, payload, status, retry_count, created_at, process_after)
    VALUES ($1, $2, $3, $4, 0, NOW(), COALESCE($5, NOW()))
  `,
    [
      tenantId,
      jobType,
      JSON.stringify(enrichedPayload),
      status,
      processAfter ? dayjs(processAfter).toDate() : null
    ]
  );

  return true;
};

module.exports = {
  claimPendingJobs,
  markJobComplete,
  rescheduleJob,
  markJobFailed,
  insertJob
};
