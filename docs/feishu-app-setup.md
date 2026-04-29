# Feishu App Setup — Stage 1 Demo

This document covers everything needed to run the two Stage 1 demo scenarios end-to-end on a real Feishu account:

| # | User action | Expected result | Pipeline exercised |
|---|---|---|---|
| 1 | Send `你好` (text) to the bot | Doubao-generated Chinese reply within **10 s** | webhook → signature → Celery → Doubao → reply |
| 2 | Send a voice message to the bot | Reply addressing the spoken content within **15 s** | scenario 1 + Volc ASR + Feishu resource download |

## Prerequisites

- A Feishu (Lark) tenant where you have permission to create custom apps. Personal accounts work via [open.feishu.cn](https://open.feishu.cn/app).
- A **publicly reachable HTTPS URL** terminating at your FastAPI server. Feishu refuses plain HTTP and self-signed certs. Pick one of:
  - Production: a real domain whose DNS A-record points at the ECS public IP, plus `certbot --nginx`. See [setup.md](setup.md).
  - Quick test: `ngrok http 8000` (gives you `https://<random>.ngrok.io`) — runs from any machine that can reach your FastAPI.
  - No-domain fallback: a free wildcard like `sslip.io` (e.g. `39-106-223-136.sslip.io`) + certbot — minutes to set up, no DNS account needed.
- A [Volcano Engine](https://www.volcengine.com/) account with **two** services activated:
  - **Ark / 火山方舟** → Doubao LLM endpoints
  - **One-shot ASR / 一句话语音识别** → voice transcription (only required for scenario 2)

---

## 1. Create the Feishu app

1. Open [Feishu Developer Console](https://open.feishu.cn/app) → **Create Custom App / 创建自建应用**
2. Fill in app name, description, icon. App type: **Custom App / 企业自建应用**
3. After creation note the **App ID** (`cli_xxxxxxxxx`) and **App Secret** (under **Credentials & Basic Info / 凭证与基础信息**) — these become `FEISHU_APP_ID` and `FEISHU_APP_SECRET` in `.env`.

## 2. Enable bot capability

1. Left sidebar → **Add Features / 添加应用能力** → enable **Bot / 机器人**
2. Set the bot's display name and avatar — this is what users see in chat.

## 3. Permissions & Scopes / 权限管理

Minimum scope for both demo scenarios:

| Scope | Why |
|---|---|
| `im:message` | Send messages as the bot (reply to the user) |
| `im:message.group_at_msg:readonly` | Receive @-mentions in group chats |
| `im:message.p2p_msg:readonly` | Receive direct messages from users |
| `im:resource` | Download voice/file/image attachments — **required for scenario 2** |
| `contact:user.base:readonly` | Resolve sender open_id → user info (used in logging) |

Tick these → **Save** at the bottom. Some scopes need admin approval; for development apps you can self-approve as the app creator.

## 4. Event subscriptions / 事件订阅

1. Left sidebar → **Event Subscription / 事件订阅** → tab **Event configuration**
2. **Encrypt Strategy** (right side) **first** — fill these before pasting the URL, otherwise URL verification fails with signature mismatch:
   - **Verification Token / 校验令牌**: click **Refresh** → copy to `.env` as `FEISHU_VERIFICATION_TOKEN`
   - **Encrypt Key / 加密密钥**: click **Refresh** → copy to `.env` as `FEISHU_ENCRYPT_KEY`
   - Restart the api service so it picks up the new tokens: `sudo systemctl restart forge-api`
3. **Request URL / 请求地址**: paste your full webhook URL (must be HTTPS):
   ```
   https://YOUR_PUBLIC_HOST/api/v1/webhook/feishu
   ```
   Feishu immediately POSTs a URL-verification challenge; the FastAPI app handles it. Green ✅ means the endpoint is reachable and signature wiring works.
4. Tab **Add events / 添加事件** → search and add:
   - `im.message.receive_v1` (接收消息 v2.0) — covers text **and** voice (Feishu uses message types under one event)

   You don't need `card.action.trigger` for the Stage 1 demo (only for interactive cards in later stages).
5. **Save** the event config.

## 5. Add the bot to a chat

The bot only sees messages from chats it's been added to.

- **Direct test (recommended for Stage 1 demo)**: In the Feishu client search the bot by name → click chat. This creates a 1-to-1 conversation; the bot receives every message you send.
- **Group test**: open any group → group settings → **Add bot / 添加机器人** → pick your bot. In groups the bot only sees @-mentions unless you also enable group-message-receive scope.

## 6. Publish / Release the app

1. Left sidebar → **Version Management & Release / 版本管理与发布**
2. **Create Version**, fill in availability range — set to "specified members" and add yourself for development.
3. Submit for release. For self-built apps in your own tenant, the admin (or you, if admin) approves immediately.

After release the bot becomes searchable in your tenant's Feishu client.

---

## 7. Doubao LLM endpoints (`DOUBAO_*`)

Both scenarios reply via Doubao.

1. Open [Volcano Ark / 火山方舟](https://console.volcengine.com/ark)
2. **API Key Management / API Key 管理** → create a key → copy to `.env` as `DOUBAO_API_KEY`
3. **Model Inference / 在线推理** → **Custom Inference Access Point / 自定义推理接入点** → create two endpoints:
   - One pointing at a Doubao Pro model (e.g., `Doubao-pro-32k`) → endpoint id like `ep-2024xxxx-yyyy` → `.env` as `DOUBAO_MODEL_PRO`
   - One pointing at a Doubao Lite model (e.g., `Doubao-lite-4k`) → another endpoint id → `DOUBAO_MODEL_LITE`
4. Set `DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3` (region default; **no trailing `/v1`** — the LangChain OpenAI client appends it automatically; see [troubleshooting.md](troubleshooting.md))

## 8. Volc ASR credentials (only for scenario 2)

1. Open [Volcano Speech / 火山引擎语音技术](https://console.volcengine.com/speech) → enable **One-shot Speech Recognition / 一句话识别**
2. Note the **App ID** → `.env` as `VOLC_ASR_APP_ID`
3. **Access Token** → `.env` as `VOLC_ASR_ACCESS_TOKEN`

If you skip these, scenario 2 will fail to transcribe (you'll see `ASRError` in `journalctl -u forge-worker`); scenario 1 still works.

---

## 9. Final `.env` checklist

After steps 1–8, your `.env` should have **non-placeholder** values for at least:

```bash
# Feishu — from steps 1–4
FEISHU_APP_ID=cli_xxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxxxxxxxx
FEISHU_ENCRYPT_KEY=xxxxxxxxxxxxxxxxxxxxxx

# Doubao — from step 7
DOUBAO_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL_PRO=ep-20241225xxxxxx-xxxxx
DOUBAO_MODEL_LITE=ep-20241225yyyyyy-yyyyy

# Volc ASR — from step 8 (scenario 2 only)
VOLC_ASR_APP_ID=12345678
VOLC_ASR_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

After editing, restart the workers so they pick up the new env:

```bash
sudo systemctl restart forge-api forge-worker
```

---

## 10. Run the demo

### Scenario 1 — text

1. Open Feishu, go to your bot's 1-to-1 chat
2. Type `你好` → press Enter
3. Within 10 s the bot replies with a Doubao-generated Chinese sentence

### Scenario 2 — voice

1. Same chat, hold the microphone button → record "今天天气怎么样" → release
2. Within 15 s the bot replies addressing the spoken content (it transcribes via Volc ASR, then runs the same LLM path)

### Live monitoring during the demo

In a separate SSH session on the server:

```bash
# Webhook arrival + signature check
sudo journalctl -u forge-api -f | grep -E "webhook|signature|dedup"

# Task pickup + LLM/ASR latency
sudo journalctl -u forge-worker -f | grep -E "received|invoke|reply|ASR"
```

Roughly what you should see:

```
forge-api: webhook_received event_id=... message_type=text
forge-api: signature_verified
forge-api: dedup_pass event_id=...
forge-api: task_dispatched task_id=... queue=slow
forge-worker: handle_message_task received task_id=...
forge-worker: doubao_invoke prompt_len=... tier=pro
forge-worker: doubao_complete latency_ms=2150
forge-worker: feishu_reply_text message_id=om_... ok=true
```

---

## 11. Troubleshooting

| Symptom | Probable cause | Fix |
|---|---|---|
| URL verification 401 in Feishu console | Encrypt Key / Verification Token in `.env` differ from console | Refresh both in console, paste into `.env`, `systemctl restart forge-api`, retry **Save** in console |
| Bot doesn't reply, no log activity | Bot not added to chat / not released to your account | Steps 5 + 6 above |
| `forge-worker` logs `ASRError: 401` | `VOLC_ASR_*` wrong or one-shot ASR not activated | Re-check step 8 |
| `forge-worker` logs `LLMError: 401` | `DOUBAO_BASE_URL` has trailing `/v1` | Remove it, restart worker |
| Reply is "抱歉，处理出错" | Exception in worker; check `journalctl -u forge-worker -n 100` | Look at the traceback — usually missing scope or wrong endpoint id |
| Voice scenario silent reply | ASR returned empty; the worker still calls LLM with empty text | Check `journalctl` for `asr_text=""` — usually Volc rejected the audio format |

See also [troubleshooting.md](troubleshooting.md) for infrastructure-level issues.
