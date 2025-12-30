const dayjs = require('dayjs');
const config = require('../config');
const logger = require('../logger');
const {
  claimPendingJobs,
  markJobComplete,
  rescheduleJob,
  markJobFailed,
  insertJob
} = require('./jobRepository');
const { getTenantConfig, findFallbackEmail } = require('../db/tenantDataGateway');
const handleSendSms = require('./handlers/sendSms');
const handleSendEmail = require('./handlers/sendEmail');
const handleNotifyCustomer = require('./handlers/notifyCustomer');

const JOB_HANDLERS = {
  send_sms: handleSendSms,
  send_email: handleSendEmail,
  notify_customer: handleNotifyCustomer
};

const parseTimeToMinutes = (timeString) => {
  if (!timeString) {
    return null;
  }

  const [hours, minutes] = timeString.split(':').map((part) => Number(part));
  if (
    Number.isNaN(hours) ||
    Number.isNaN(minutes) ||
    hours < 0 ||
    hours > 23 ||
    minutes < 0 ||
    minutes > 59
  ) {
    return null;
  }

  return hours * 60 + minutes;
};

const isWithinQuietHours = (currentMinutes, start, end) => {
  if (start === null || end === null) {
    return false;
  }

  if (start < end) {
    return currentMinutes >= start && currentMinutes < end;
  }

  if (start > end) {
    return currentMinutes >= start || currentMinutes < end;
  }

  return false;
};

class JobProcessor {
  constructor(options = {}) {
    this.pollIntervalMs = options.pollIntervalMs || config.pollIntervalMs;
    this.maxConcurrentJobs =
      options.maxConcurrentJobs || config.maxConcurrentJobs;
    this.activeJobs = 0;
    this.timer = null;
  }

  start() {
    if (this.timer) {
      return;
    }

    this.timer = setInterval(() => {
      this.tick().catch((error) => {
        logger.error({ err: error }, 'Job polling tick failed');
      });
    }, this.pollIntervalMs);

    // Kick off immediately
    this.tick().catch((error) => {
      logger.error({ err: error }, 'Initial job poll tick failed');
    });
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async tick() {
    if (this.activeJobs >= this.maxConcurrentJobs) {
      return;
    }

    const availableSlots = this.maxConcurrentJobs - this.activeJobs;
    const jobs = await claimPendingJobs(availableSlots);
    if (!jobs.length) {
      return;
    }

    jobs.forEach((job) => {
      this.activeJobs += 1;
      this.runJob(job).finally(() => {
        this.activeJobs -= 1;
      });
    });
  }

  async runJob(job) {
    try {
      const tenantConfig = await getTenantConfig(job.tenant_id);
      const quietHoursDelay = this.getQuietHoursDelay(job, tenantConfig);
      if (quietHoursDelay) {
        await rescheduleJob({
          jobId: job.id,
          retryCount: job.retry_count,
          processAfter: quietHoursDelay,
          lastError: 'Deferred for quiet hours',
          status: 'pending'
        });
        logger.info(
          { jobId: job.id, tenantId: job.tenant_id },
          'Deferred job due to quiet hours'
        );
        return;
      }

      const handler = JOB_HANDLERS[job.job_type];
      if (!handler) {
        throw new Error(`Unsupported job type: ${job.job_type}`);
      }

      const result = await handler(job, {
        tenantConfig,
        logger
      });

      await markJobComplete(job.id, result?.reason);
      logger.info(
        { jobId: job.id, type: job.job_type },
        'Job processed successfully'
      );
    } catch (error) {
      await this.handleJobFailure(job, error);
    }
  }

  getQuietHoursDelay(job, tenantConfig) {
    if (job.payload?.urgent) {
      return null;
    }

    const start = parseTimeToMinutes(tenantConfig.quietHoursStart);
    const end = parseTimeToMinutes(tenantConfig.quietHoursEnd);

    if (start === null || end === null) {
      return null;
    }

    const now = dayjs();
    const currentMinutes = now.hour() * 60 + now.minute();

    if (!isWithinQuietHours(currentMinutes, start, end)) {
      return null;
    }

    let nextAllowed = now
      .hour(Math.floor(end / 60))
      .minute(end % 60)
      .second(0)
      .millisecond(0);

    if (start > end) {
      // Quiet hours wrap past midnight
      if (currentMinutes >= start) {
        nextAllowed = nextAllowed.add(1, 'day');
      }
    } else if (currentMinutes >= end) {
      nextAllowed = nextAllowed.add(1, 'day');
    }

    if (nextAllowed.isBefore(now)) {
      nextAllowed = nextAllowed.add(1, 'day');
    }

    return nextAllowed.toDate();
  }

  async handleJobFailure(job, error) {
    logger.error(
      { err: error, jobId: job.id, jobType: job.job_type },
      'Job processing failed'
    );

    const attempts = (job.retry_count || 0) + 1;
    const nextRetryAt = dayjs()
      .add(config.retryDelayMinutes, 'minute')
      .toDate();

    if (attempts < config.maxRetries) {
      await rescheduleJob({
        jobId: job.id,
        retryCount: attempts,
        processAfter: nextRetryAt,
        lastError: error.message || 'Unknown error',
        status: 'pending'
      });
      job.retry_count = attempts;
      return;
    }

    if (job.job_type === 'send_sms') {
      const fallbackResult = await this.tryEmailFallback(job, error);
      if (fallbackResult) {
        return;
      }
    }

    await markJobFailed(job.id, error.message || 'Unknown error');
  }

  async tryEmailFallback(job, error) {
    const customerId = job.payload?.customer_id;
    if (!customerId) {
      await markJobFailed(
        job.id,
        `SMS failed after retries: ${error.message}`
      );
      return true;
    }

    const fallbackEmail = await findFallbackEmail(job.tenant_id, customerId);
    if (!fallbackEmail) {
      await markJobFailed(
        job.id,
        `SMS failed, no fallback email for customer ${customerId}`
      );
      return true;
    }

    const payload = {
      to: fallbackEmail,
      subject: job.payload.subject || 'SMS Fallback Notification',
      body: job.payload.body,
      source_job_id: job.id,
      source_reference: `sms_fallback_${job.id}`
    };

    await insertJob({
      tenantId: job.tenant_id,
      jobType: 'send_email',
      payload,
      sourceReference: payload.source_reference
    });

    await markJobFailed(
      job.id,
      `SMS failed but fallback email scheduled for ${fallbackEmail}`,
      'failed_fallback_email'
    );

    logger.warn(
      { jobId: job.id, tenantId: job.tenant_id },
      'Created fallback email job'
    );
    return true;
  }
}

module.exports = JobProcessor;
