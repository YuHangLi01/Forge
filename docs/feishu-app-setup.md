# Feishu App Setup

## 1. Create application

Go to [Feishu Developer Console](https://open.feishu.cn/app) and create a new custom app.

## 2. Enable permissions

Under **Permissions & Scopes**, enable:

- `im:message` — read and send messages
- `im:message.group_at_msg` — receive group at-mentions
- `docx:document` — create and edit documents
- `drive:drive` — upload files to Drive
- `contact:user.base:readonly` — read user basic info

## 3. Configure event subscriptions

Under **Event Subscriptions**:
1. Set the webhook URL to your ngrok HTTPS URL + `/api/v1/webhook/feishu`
2. Set the **Verification Token** — copy this to `FEISHU_VERIFICATION_TOKEN`
3. Set the **Encrypt Key** — copy this to `FEISHU_ENCRYPT_KEY`
4. Subscribe to events:
   - `im.message.receive_v1` (receive messages)
   - `card.action.trigger` (interactive card callbacks)

## 4. Bot capabilities

Under **Bot**, enable the bot capability so the app can send messages.

## 5. Get App ID and Secret

Under **Credentials & Basic Info**:
- Copy **App ID** to `FEISHU_APP_ID`
- Copy **App Secret** to `FEISHU_APP_SECRET`

## 6. Publish the app

Request approval or, for development apps, add test users under **Version Management & Release**.
