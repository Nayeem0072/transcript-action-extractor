# API Documentation

REST API for pipeline runs: create a run (upload meeting transcript + metadata), then subscribe to a Server-Sent Events (SSE) stream for real-time progress. Currently only the **extractor** stage runs; normalizer and executor are not yet wired.

**Base URL (local):** `http://localhost:8000`  
**Interactive docs:** `http://localhost:8000/docs`

Start the server from the project root:

```bash
python run_api.py
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/runs` | Create a new pipeline run. Upload a file (or pass by reference), start processing, get `runId` and `streamUrl`. |
| `GET`  | `/runs/{runId}/stream` | SSE stream for real-time progress (extractor steps). |

---

## POST /runs

Create a pipeline run. Processing starts asynchronously; use the returned `streamUrl` to consume progress via SSE.

### Request

**Content-Type:** either `multipart/form-data` or `application/json` (for upload by reference).

#### Option A: Multipart (file upload)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Meeting transcript. Allowed: `.txt`, `.csv`, `.pdf`, `.doc`. Max size: **15 MB**. |
| `meetingDate` | string | No | Date of the meeting, e.g. `YYYY-MM-DD`. |
| `language` | string | No | Language code, e.g. `en`, `bn`. |

**Example (curl):**

```bash
curl -X POST http://localhost:8000/runs \
  -F "file=@/path/to/transcript.txt" \
  -F "meetingDate=2026-03-07" \
  -F "language=en"
```

#### Option B: JSON (upload by reference)

Use when the file is already on the server (e.g. from a previous upload). Send `Content-Type: application/json`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fileRef` | string | Yes | Path to the file: absolute path, or filename under the server’s `uploads/` directory. |
| `meetingDate` | string | No | Date of the meeting, e.g. `YYYY-MM-DD`. |
| `language` | string | No | Language code, e.g. `en`, `bn`. |

**Example:**

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"fileRef": "abc123.txt", "meetingDate": "2026-03-07", "language": "en"}'
```

### Response

**Status:** `201 Created`

**Body (JSON):**

| Field | Type | Description |
|-------|------|-------------|
| `runId` | string | Unique id for this run. Use it in the stream URL. |
| `streamUrl` | string | Path to the SSE stream, e.g. `GET /runs/{runId}/stream`. |

**Example:**

```json
{
  "runId": "a1b2c3d4e5f6",
  "streamUrl": "/runs/a1b2c3d4e5f6/stream"
}
```

### Errors

| Status | Condition |
|--------|-----------|
| `400` | Missing `file` (multipart) or `fileRef` (JSON); or file type not allowed (allowed: `.txt`, `.csv`, `.pdf`, `.doc`). |
| `404` | JSON body: `fileRef` points to a path that does not exist. |
| `413` | File larger than 15 MB. |

---

## GET /runs/{runId}/stream

Real-time progress for the run. Streams Server-Sent Events until the pipeline finishes or errors.

### Request

| Item | Value |
|------|--------|
| **Path** | `runId` — from `POST /runs` response. |
| **Headers** | `Accept: text/event-stream` (recommended). |

**Example (curl):**

```bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8000/runs/a1b2c3d4e5f6/stream
```

### Response

**Status:** `200 OK`

**Headers:**

| Header | Value |
|--------|--------|
| `Content-Type` | `text/event-stream` |
| `Cache-Control` | `no-cache` |
| `Connection` | `keep-alive` |

**Body:** SSE stream. Each message has an optional `event` type and a `data` line (JSON).

### SSE event types

| Event | Description | Data payload |
|-------|-------------|--------------|
| `progress` | An agent is working on a step. | `agent`, `step`, `status`; optional `current`, `total` (e.g. chunks 8/11). |
| `step_done` | One step of an agent finished. | `agent`, `step`. |
| `agent_done` | Entire agent finished. | `agent` (`"extractor"` \| `"normalizer"` \| `"executor"`). |
| `run_complete` | Whole pipeline finished. | Optional `summary` (e.g. `actions_extracted`). |
| `error` | Run or step failed. | `message`; optional `code`, `agent`, `step`. |

### Extractor steps (SSE `step` values)

Progress follows the extractor graph nodes so the frontend can show accurate steps:

| Step | Description |
|------|-------------|
| `load_transcript` | Load transcript from the uploaded/referenced file. |
| `segmenter` | Split transcript into chunks (by speaker turns, 20 turns per chunk). |
| `chunks` | Progress event when segmenter is done (no current/total). |
| `parallel_extractor` | Extract segments from each chunk (LLM). Progress events with `current`/`total` (e.g. 7/12) as each chunk completes. |
| `evidence_normalizer` | Clean ASR noise, drop meta-actions, convert segments to actions. |
| `cross_chunk_resolver` | Merge cross-chunk duplicates, resolve vague references. |
| `global_deduplicator` | Remove duplicate actions by similarity. |
| `action_finalizer` | Schema enforcement, sort, drop low-confidence. |

### Example stream (extractor, node-level)

```
event: progress
data: {"agent": "extractor", "step": "load_transcript", "status": "running"}

event: step_done
data: {"agent": "extractor", "step": "load_transcript"}

event: step_done
data: {"agent": "extractor", "step": "segmenter"}

event: progress
data: {"agent": "extractor", "step": "chunks", "status": "running"}

event: progress
data: {"agent": "extractor", "step": "parallel_extractor", "status": "running", "current": 1, "total": 12}

event: progress
data: {"agent": "extractor", "step": "parallel_extractor", "status": "running", "current": 2, "total": 12}

… (further parallel_extractor progress: 3/12, 4/12, …)

event: step_done
data: {"agent": "extractor", "step": "parallel_extractor"}

event: step_done
data: {"agent": "extractor", "step": "evidence_normalizer"}

event: step_done
data: {"agent": "extractor", "step": "cross_chunk_resolver"}

event: step_done
data: {"agent": "extractor", "step": "global_deduplicator"}

event: step_done
data: {"agent": "extractor", "step": "action_finalizer"}

event: agent_done
data: {"agent": "extractor"}

event: run_complete
data: {"summary": {"actions_extracted": 5}}
```

### Errors

| Status | Condition |
|--------|-----------|
| `404` | `runId` not found (invalid or run never created). |

---

## Pipeline (current behavior)

Only the **extractor** stage runs. Progress is emitted at **node level** (segmenter, parallel_extractor with chunk progress like 7/12, evidence_normalizer, cross_chunk_resolver, global_deduplicator, action_finalizer). Normalizer and executor are not executed yet.
