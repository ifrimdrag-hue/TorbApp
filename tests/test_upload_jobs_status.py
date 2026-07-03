"""Regression tests for cross-worker upload-job status.

Bug: upload-job status was tracked in a per-process in-memory dict. Under
multiple gunicorn workers, a status poll landing on a worker that never saw
the job wrongly reported "server restarted", even though the import succeeded.

Fix: job state is persisted to the `upload_jobs` table, so any worker (here
simulated by a direct DB write the request handler never saw in memory) can
answer the poll.
"""
import json
import sqlite3


def _insert_job(db_path, job_id, status, mesaj=None, randuri=None, avertisment=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO upload_jobs "
        "(job_id, tip, fisier, status, mesaj, randuri, avertisment, actualizat_la) "
        "VALUES (?,?,?,?,?,?,?, datetime('now','localtime')) "
        "ON CONFLICT(job_id) DO UPDATE SET "
        "status=excluded.status, mesaj=excluded.mesaj, randuri=excluded.randuri, "
        "avertisment=excluded.avertisment",
        (job_id, 'vanzari', 'Vanzari.xlsx', status, mesaj, randuri, avertisment),
    )
    conn.commit()
    conn.close()


def test_status_reads_job_written_by_another_worker(client, db_path):
    # Simulate the owning worker having recorded a completed job in SQLite.
    _insert_job(db_path, 'JOB-CROSSWORKER', 'done',
                mesaj='Import finalizat: 135420 rânduri', randuri=135420)

    resp = client.get('/api/upload/status/JOB-CROSSWORKER')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'done'
    assert data['randuri'] == 135420
    assert 'repornit' not in (data.get('mesaj') or ''), \
        "must not show the false 'server restarted' message for a known job"


def test_status_unknown_job_returns_not_found_message(client):
    resp = client.get('/api/upload/status/does-not-exist')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'error'
    assert 'negăsit' in data['mesaj']
