# Jobs Endpoint

## GET /jobs/{job_id}

Retrieve a job record directly from the job store. Returns a subset of fields compared to the async status endpoint — no `result` or `error_message`.

**Auth:** required (no specific scope).

**Path parameter:** `job_id` — UUID

**Response `200`:**
```json
{
  "job_id": "550e8400-...",
  "status": "succeeded",
  "model": "echo",
  "version": "v1",
  "created_at": "2026-04-27T15:00:00+00:00"
}
```

**Errors:** `404` if job not found (raised as `KeyError` by the job store).

---

For full job details including result and error, use [`GET /predict/async/{job_id}`](inference.md#get-predictasyncjob_id).
