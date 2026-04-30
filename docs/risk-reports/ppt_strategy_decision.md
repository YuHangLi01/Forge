# PPT Strategy Decision

> **Status: Decision recorded. Default Stage 1 path is Option B (python-pptx → Drive upload). Probe results from Option A may shift Stage 2 strategy.**

## Background

Stage 1 must produce slide decks from a structured outline (typically the
output of an LLM call summarising a meeting / topic). Three credible paths
exist; each has different UX, capability, and operational trade-offs. This
document records the choice for Stage 1 and the trigger for revisiting it.

## Options

### Option A — Feishu native Slides API

Use `/open-apis/slides/v1/presentations/...` to create a deck inside
Feishu, add pages, set titles, insert bullet lists / images / charts via
Feishu's own object model.

**Pros**
- Best UX: the deck is a first-class Feishu resource, editable in-place
  in the user's browser, share/comment/version-history works natively.
- Consistent with the Doc path (we already use Feishu OpenAPI for docs).
- No transcoding lossiness — what the user sees in Feishu is exactly
  what the API created.

**Cons**
- API surface is younger and less stable than the Doc API.
- Per-element model (background, text frames, layouts) is more complex
  than the Doc block model — more edge cases to handle.
- Coverage of common PPT features (chart types, animations, slide
  layouts) is limited compared with native PPT.
- Probe results required to confirm which operations actually work.

### Option B — python-pptx → Feishu Drive upload

Build the .pptx locally with `python-pptx` (deterministic, fully
controllable), then upload as a binary file to Feishu Drive. The user
opens the file in Feishu's online viewer or downloads it for editing.

**Pros**
- Mature library; everything PowerPoint can express, python-pptx can
  express.
- Pure offline build — the `PptxBuilder` is fully unit-testable, no
  network dependency.
- No Feishu API surface risk for the build phase.
- Predictable failure modes: either the build succeeds or it doesn't.

**Cons**
- The deck is a *file*, not a Feishu-native resource — collaborative
  editing in Feishu's online viewer may be limited or read-only.
- Updating a slide requires rebuilding and re-uploading the whole file
  (no per-slide patch).
- Adds a Drive upload step (and quota) for every generation.

### Option C — Hybrid (auto-select per outline complexity)

Simple, bullet-only outlines go to Feishu native (Option A); decks that
need charts / images / custom layouts fall through to python-pptx (B).

**Pros**
- Best per-deck UX where Feishu native is sufficient.

**Cons**
- Two code paths to maintain.
- Decision logic must accurately predict what Feishu can render — getting
  it wrong drops users into a half-rendered native deck.
- Doubles test surface.
- Premature for Stage 1 — defer until we have data on what users actually
  generate.

## Decision: Option B for Stage 1

**Rationale:**

1. **Time-to-demo**: python-pptx is a known quantity; our `PptxBuilder`
   was built and tested in under a day. Option A would have required
   probing before we could even commit to the schema.
2. **Risk profile**: Stage 1 has hard verification criteria (5 demo decks
   building cleanly, deterministic CI). Option A's API maturity
   uncertainty is incompatible with that.
3. **Reversibility**: Option B leaves the door open for A or C later —
   the `PPTService.create_from_outline` signature already allows passing
   a different builder. Switching costs a `PPTService(builder=...)` line
   change at the caller.
4. **Drive upload cost**: low. A 40 KB .pptx per meeting times a few
   meetings per week is well below Feishu Drive quotas.

**What we shipped (Stage 1)**

- `app/integrations/python_pptx/builder.py` — pure builder, slide schema → bytes.
- `app/services/ppt_service.py` — async wrapper, writes bytes; can route
  to `_upload_to_drive` once `FeishuAdapter.upload_drive_file` lands.
- `app/services/ppt_outline_loader.py` — JSON → `SlideSchema` list.
- `scripts/build_demo_pptx.py` — builds 5 demo decks from
  `tests/fixtures/outlines/*.json` to `out/pptx/`.
- 14 unit tests covering build / loader / async wrapper.

**What we deliberately did NOT ship**

- Feishu Drive upload of the produced .pptx (`FeishuAdapter.upload_drive_file`
  is a stub, returns empty token). Tracked as Stage 2 follow-up.
- `PPTService.patch_slide` — raises `NotImplementedError` with a comment
  pointing to Stage 2's Slides API decision.
- Image / chart insertion. Outlines today are text-only.

## When to revisit

Move from Option B → A (or C) if **any** of the following becomes true:

1. Probe (`scripts/probe_feishu_slide_api.py`) shows ≥ 8 of 10 operations
   pass with stable latency. (Run probe on the server, save report under
   `out/probe/feishu_slide_api_<timestamp>.json`.)
2. User feedback consistently asks "I want to edit this deck inside
   Feishu without downloading it."
3. We need per-slide patching for a streaming-generation UX (LLM updates
   slide 7 while user is reading slide 5).

## Probe runbook

```bash
# On the server, with valid creds + slides:slides scope on the app:
uv run python scripts/probe_feishu_slide_api.py [--folder-token TOKEN]

# Output: stdout summary + JSON report under out/probe/
# If ≥ 8 operations pass, file an issue tagged stage2/ppt-strategy
# proposing the migration to Option A.
```

## Probe results (FILL ME after running)

Date run: *t.b.d.*
Deck token: *t.b.d.*
Latency P50: *t.b.d.* ms
Latency P95: *t.b.d.* ms

| Operation | HTTP | Feishu code | Latency ms | OK? |
|---|---|---|---|---|
| create_deck | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| list_layouts | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| add_page | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| set_title | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| set_bullets | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| insert_image | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| insert_chart | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| patch_page | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| delete_page | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |
| get_share_url | *t.b.d.* | *t.b.d.* | *t.b.d.* | ☐ |

## Owners

- Stage 1 implementation (Option B) — backend
- Probe execution & report fill — backend (any team member)
- Stage 2 decision — architecture review with PMO + product
