# Feishu Doc API Findings

> **Status: Template — fill `Observations` after running `scripts/smoke_doc_api.py` against a real Feishu app.**
> The numbers below in *italics* are placeholders to be replaced with the
> latency / error code / batch limits actually observed.

## Goal of this report

Capture hard, reproducible evidence about the Feishu Doc API surface the
project depends on, so we know:

1. What works today and what doesn't.
2. What the realistic latency and rate-limit envelope is.
3. What markdown features we can't render and need workarounds for.
4. Any failure modes that should be reflected in the runbook.

The Doc API is the primary write path for `FeishuDocService.create_from_markdown`
(used by both the meeting-minute demo and any future doc-creation feature).

## How the data was collected

```bash
# On a host with valid Feishu app creds
uv run python scripts/smoke_doc_api.py tests/fixtures/meetings/01_requirements.md

# Repeat for the other 4 meeting fixtures
for f in tests/fixtures/meetings/*.md; do
    uv run python scripts/smoke_doc_api.py "$f"
    sleep 2  # respect rate limits
done
```

The script logs `doc_id`, `share_url`, `sections`, and `latency_ms` per
run; `sudo journalctl -u forge-api` (when invoked through the service) or
the script's stdout (when invoked directly) is the source of truth for
per-call telemetry.

## Observations (FILL ME)

### 1. End-to-end latency

| Fixture | Markdown size (chars) | `create_document` ms | `batch_update_blocks` ms | `get_document_blocks` ms | total ms |
|---|---|---|---|---|---|
| 01_requirements | 3344 | *t.b.d.* | *t.b.d.* | *t.b.d.* | *t.b.d.* |
| 02_granularity | 3765 | *t.b.d.* | *t.b.d.* | *t.b.d.* | *t.b.d.* |
| 03_midterm_review | 3483 | *t.b.d.* | *t.b.d.* | *t.b.d.* | *t.b.d.* |
| 04_project_pr | 3731 | *t.b.d.* | *t.b.d.* | *t.b.d.* | *t.b.d.* |
| 05_defense | 4805 | *t.b.d.* | *t.b.d.* | *t.b.d.* | *t.b.d.* |

Aggregate (5 docs):
- **P50**: *t.b.d.* ms
- **P95**: *t.b.d.* ms
- **Max**: *t.b.d.* ms

### 2. Block count per fixture

How many Feishu blocks does our `md_to_feishu_blocks` converter produce
per fixture? This drives `batch_update_blocks` payload size.

| Fixture | block count | block types observed (counts) |
|---|---|---|
| 01_requirements | *t.b.d.* | *t.b.d.* |
| 02_granularity | *t.b.d.* | *t.b.d.* |
| 03_midterm_review | *t.b.d.* | *t.b.d.* |
| 04_project_pr | *t.b.d.* | *t.b.d.* |
| 05_defense | *t.b.d.* | *t.b.d.* |

### 3. Markdown features successfully rendered

Confirmed by visual inspection of the resulting Feishu Doc:

- [ ] H1 / H2 / H3 headings → block_type 3/4/5
- [ ] Paragraphs → block_type 2
- [ ] Bullet lists (1 level) → block_type 12
- [ ] Bullet lists (2 levels)
- [ ] Bullet lists (3 levels)
- [ ] Ordered lists → block_type 13
- [ ] Code blocks → block_type 14
- [ ] Tables → block_type 31
- [ ] Bold / italic / inline-code inline markers
- [ ] Links

### 4. Markdown features NOT supported / degraded

To be filled. Suspected:
- HTML inline tags
- Mermaid blocks (no native support; should fall back to code block)
- Image embeds without `image_token`
- Math (KaTeX/LaTeX)

When degraded, the converter currently falls back to a plain `Text` block.
Document the fallback in the user-facing setup guide if this turns out to
be visible.

### 5. Rate limits hit

Observed Feishu rate-limit responses (code `99991663` or HTTP 429) when
running 5 docs back-to-back? **Yes / No**

If yes, document the wait between calls that avoids it.

### 6. `batch_update_blocks` payload size limit

Sample doc with many blocks (e.g. table-heavy fixture): does Feishu reject
when the request body exceeds N MB / N blocks? Record the threshold.

- Largest fixture: *t.b.d.* blocks, *t.b.d.* KB request body — **OK / 413 / 99991xxx**

### 7. `get_document_blocks` read-back latency

Already covered in §1. Note here whether the response paginates and at
what page size.

## Decisions (post-fill)

After collecting the data, update the following:

1. **`FeishuDocService` resilience**: do we need to chunk `batch_update_blocks`
   into smaller batches if a fixture exceeds the limit?
2. **Concurrency budget**: how many Doc creations / minute can we sustain
   without throttling? This caps the meeting-minute auto-generation flow.
3. **Markdown converter gaps**: which markdown features should we add or
   document as unsupported?

## Action items

- [ ] (owner: backend) Run `smoke_doc_api.py` on all 5 fixtures, fill §1-§7.
- [ ] (owner: backend) If §6 reveals a hard limit, add chunking to
      `FeishuDocService.create_from_markdown`.
- [ ] (owner: docs) Mirror the supported / unsupported markdown table into
      `docs/feishu-app-setup.md` so users know what to expect.
- [ ] (owner: PMO) File issue for any `t.b.d.` row that turns out blocking.
