import json
from datetime import datetime, timedelta
from src.db.central_db import with_transaction, query


def parse_job_row(row):
    """Parse a job row from the database."""
    payload = row['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)

    return {
        'id': row['id'],
        'tenant_id': row['tenant_id'],
        'job_type': row['job_type'],
        'payload': payload,
        'status': row['status'],
        'retry_count': row.get('retry_count', 0),
        'last_error': row.get('last_error'),
        'created_at': row['created_at'],
        'process_after': row.get('process_after')
    }


def claim_pending_jobs(limit):
    """Claim pending jobs using SELECT FOR UPDATE SKIP LOCKED."""
    if not limit:
        return []

    with with_transaction() as client:
        select_query = """
            SELECT *
            FROM communication_jobs
            WHERE status = 'pending'
              AND (process_after IS NULL OR process_after <= NOW())
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT %s
        """

        rows = client.query(select_query, [limit])

        if not rows:
            return []

        ids = [row['id'] for row in rows]
        client.query(
            """
            UPDATE communication_jobs
            SET status = 'processing'
            WHERE id = ANY(%s::bigint[])
            """,
            [ids]
        )

        return [parse_job_row(row) for row in rows]


def mark_job_complete(job_id, note=None):
    """Mark a job as complete."""
    query(
        """
        UPDATE communication_jobs
        SET status = 'complete',
            last_error = %s
        WHERE id = %s
        """,
        [note, job_id]
    )


def reschedule_job(job_id, retry_count, process_after, last_error, status='pending'):
    """Reschedule a job for later processing."""
    query(
        """
        UPDATE communication_jobs
        SET status = %s,
            retry_count = %s,
            process_after = %s,
            last_error = %s
        WHERE id = %s
        """,
        [status, retry_count, process_after, last_error, job_id]
    )


def mark_job_failed(job_id, last_error, status='failed'):
    """Mark a job as failed."""
    query(
        """
        UPDATE communication_jobs
        SET status = %s,
            last_error = %s
        WHERE id = %s
        """,
        [status, last_error, job_id]
    )


def job_exists_for_reference(tenant_id, job_type, reference):
    """Check if a job already exists for a given source reference.

    Uses the source_reference column if available (faster), falls back to
    payload JSONB query for backwards compatibility.
    """
    if not reference:
        return False

    # Use the dedicated column (faster with unique index)
    # Falls back to payload check for backwards compatibility
    rows = query(
        """
        SELECT 1
        FROM communication_jobs
        WHERE tenant_id = %s
          AND job_type = %s
          AND (source_reference = %s OR payload ->> 'source_reference' = %s)
          AND status IN ('pending', 'processing', 'complete')
        LIMIT 1
        """,
        [tenant_id, job_type, reference, reference]
    )

    return len(rows) > 0


def insert_job(tenant_id, job_type, payload, process_after=None, status='pending', source_reference=None):
    """Insert a new job into the queue.

    Stores source_reference in both a dedicated column (for fast lookups)
    and the payload (for backwards compatibility).
    """
    enriched_payload = dict(payload)

    reference = source_reference or payload.get('source_reference')
    if reference:
        enriched_payload['source_reference'] = reference

    if reference and job_exists_for_reference(tenant_id, job_type, reference):
        return None

    process_after_value = process_after if process_after else datetime.now()

    query(
        """
        INSERT INTO communication_jobs
          (tenant_id, job_type, payload, status, retry_count, created_at, process_after, source_reference)
        VALUES (%s, %s, %s, %s, 0, NOW(), %s, %s)
        """,
        [
            tenant_id,
            job_type,
            json.dumps(enriched_payload),
            status,
            process_after_value,
            reference
        ]
    )

    return True


def create_job(tenant_id, job_type, payload, process_after=None, status='pending', source_reference=None):
    """
    Create a new job and return its ID.

    Similar to insert_job but returns the created job's ID.
    Stores source_reference in both a dedicated column (for fast lookups)
    and the payload (for backwards compatibility).
    """
    enriched_payload = dict(payload)

    reference = source_reference or payload.get('source_reference')
    if reference:
        enriched_payload['source_reference'] = reference

    if reference and job_exists_for_reference(tenant_id, job_type, reference):
        return None

    process_after_value = process_after if process_after else datetime.now()

    rows = query(
        """
        INSERT INTO communication_jobs
          (tenant_id, job_type, payload, status, retry_count, created_at, process_after, source_reference)
        VALUES (%s, %s, %s, %s, 0, NOW(), %s, %s)
        RETURNING id
        """,
        [
            tenant_id,
            job_type,
            json.dumps(enriched_payload),
            status,
            process_after_value,
            reference
        ]
    )

    return rows[0]['id'] if rows else None
