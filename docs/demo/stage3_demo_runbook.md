# Stage 3 Demo Runbook

## Pre-Demo Checklist (T-30 min)

- [ ] `uv run pytest -m demo_critical --no-cov -q` — all green
- [ ] Redis running: `redis-cli ping` → PONG
- [ ] PostgreSQL running, migrations applied: `alembic current` shows head
- [ ] Celery worker: `celery -A app.tasks.celery_app inspect active` (≥1 worker)
- [ ] Env vars set: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_ENCRYPT_KEY`, `DOUBAO_API_KEY`
- [ ] `FORGE_USE_GRAPH=true`, `FORGE_STAGE=3`
- [ ] Feishu bot visible in target group chat; test ping with `/ping`

---

## Demo Script (7 steps)

### Step 1 — Doc pipeline (3 min)

**User action:** Send to bot: "帮我写一份市场分析报告，面向高管，专业简洁风格"

Expected:
- Progress card appears: "🧠 理解意图…" → "📄 生成文档大纲…" → "✍️ 生成内容…"
- Plan preview card with 3 steps; user clicks **确认执行**
- Final card: document link (opens Feishu doc with ≥3 sections)

Backend logs: `intent_parsed`, `planner_plan_created`, `feishu_doc_write_done`

**If LLM is slow:** The progress card updates in real-time — reassure audience it's streaming.

---

### Step 2 — PPT pipeline (3 min)

**User action:** "帮我做一份市场分析PPT，5页，高管受众"

Expected:
- Progress: ppt_structure_gen → ppt_content_gen → feishu_ppt_write
- Artifact card with Feishu Drive link (downloads .pptx)

Backend logs: `ppt_brief_generated`, `ppt_content_generated`, `pptx_uploaded`

**If upload fails:** Show slides JSON in logs; explain Feishu token scope.

---

### Step 3 — Lego multi-format (4 min)

**User action:** "同时生成一份市场分析报告和一份PPT"

Expected:
- scenario_composer sets `_lego_scenarios=["C","D"]`
- lego_orchestrator builds 6-step plan
- Executes strictly serially: doc chain first, then ppt chain
- Two artifact cards appear in sequence

Backend logs: `scenario_composer_done`, `lego_plan_composed`, then doc logs then ppt logs

---

### Step 4 — Mid-execution pause (2 min)

**User action:** Start a long doc generation, then immediately send "等等"

Expected:
- After current node completes, pause card appears: completed steps ✅, pending steps ⏸
- Three buttons: ▶️继续 / ✏️修改文档 / ❌取消

**User action:** Click **▶️继续**

Expected: Execution resumes from the next pending step.

Backend logs: `execution_paused`, `graph_resumed_from_pause`

**If pause card doesn't appear:** The graph may have already finished — use "等等" earlier.

---

### Step 5 — Slide edit (2 min)

**User action:** After Step 2, send "把第2张改成英文"

Expected:
- ppt_slide_editor updates slide 2 content
- New PPT artifact card with updated content

---

### Step 6 — Calendar disambiguation (2 min)

**User action:** "明天开会前整理一份简报"

Expected (if user has ≥2 calendar events tomorrow):
- Clarify card listing related events: "请确认是哪个会议？"
- User selects one → doc generated for that event

**If user has no calendar permissions:** Falls back to V1 prompt silently.

---

### Step 7 — Cross-product modification (2 min)

**User action:** After Steps 1+2, send "改一下第2个" (ambiguous)

Expected:
- clarify card: "📄 文档第2节 | 📊 PPT第2页 | 📄+📊 都改"
- User clicks "📊 PPT第2页" → ppt_slide_editor runs

---

## Failure Playbook

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| No progress card | Celery worker down | `! supervisorctl restart celery` |
| "解析失败" intent | LLM quota exceeded | Switch `DOUBAO_API_KEY` to backup |
| PPT upload 403 | Drive token expired | Re-authorize app in Feishu console |
| Graph loops forever | step_router infinite loop | Check completed_steps in Redis |
| Calendar 403 | Missing `calendar:event:readonly` scope | Skip Step 6, mention "pending permission" |

---

## Post-Demo Talking Points

- **LangSmith trace:** Show the span timeline with `forge_node`, `duration_ms`
- **Pause/resume:** Explain checkpoint_control is a first-class graph node, not an external hook
- **Serial lego:** Each scenario runs end-to-end before the next starts — no race conditions
- **Prompt versioning:** V1 always CURRENT; V2 calendar/disambiguation registered non-current
