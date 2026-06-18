# HiPi Webhook 转发

在 HiPi「状态」页配置 **Webhook URL** 与可选 **签名密钥** 后，收到可转发的入站短信时会向该 URL 发送 `POST` 请求。

## 请求格式

- **Method**: `POST`
- **Content-Type**: `application/json; charset=utf-8`
- **Body**（UTF-8 JSON）示例：

```json
{
  "event": "inbound_sms",
  "from": "+8613800138000",
  "from_name": "张三",
  "body": "你好",
  "timestamp": "2025-06-17T10:00:00+00:00",
  "message_id": 42
}
```

| 字段 | 说明 |
|------|------|
| `event` | 固定为 `inbound_sms` |
| `from` | 发件人号码（E.164） |
| `from_name` | 本地联系人姓名，未匹配时为 `null` |
| `body` | 短信正文 |
| `timestamp` | 消息入库时间（UTC ISO 8601） |
| `message_id` | HiPi 本地数据库 ID |

仅转发**纯文本短信**；彩信、空消息、状态报告等会被跳过（与号码转发规则一致）。

## HMAC 签名（可选）

配置签名密钥后，HiPi 会附加以下请求头：

| 请求头 | 说明 |
|--------|------|
| `X-HiPi-Timestamp` | Unix 秒级时间戳（字符串） |
| `X-HiPi-Signature` | `sha256=<hex>`，HMAC-SHA256 |

**签名字符串**（UTF-8）：

```
{timestamp}.{raw_json_body}
```

即：时间戳 + `.` + **原始 JSON 正文**（与 HTTP body 字节完全一致，含中文与字段顺序）。

> 注意：Python `urllib` 发出的头名在部分客户端中可能显示为小写（如 `x-hipi-signature`），验签时请做**大小写不敏感**匹配。

### 服务端验签步骤

1. 读取原始请求体字节 `body`（不要做 JSON 重排后再验签）
2. 取 `X-HiPi-Timestamp`、`X-HiPi-Signature` 头
3. 拒绝时间戳与当前时间相差超过 **5 分钟** 的请求（防重放）
4. 用共享密钥计算 `HMAC-SHA256("{timestamp}.{body_utf8}")`
5. 与 `X-HiPi-Signature` 中 `sha256=` 后的十六进制值做**常量时间**比较

HiPi 提供 `hipi.webhook.verify_webhook_request()` 可直接用于自建服务。

### Python 验签示例

```python
from hipi.webhook import verify_webhook_request

SECRET = "your-shared-secret"

def handle_post(environ, start_response):
    body = environ["wsgi.input"].read()
    headers = {k: v for k, v in environ.items() if k.startswith("HTTP_")}
    # 简化：Flask/FastAPI 请用 request.get_data() 与 request.headers

    if not verify_webhook_request(SECRET, body, headers, max_age_sec=300):
        start_response("401 Unauthorized", [])
        return [b"invalid signature"]

    # ... 处理 JSON ...
    start_response("200 OK", [])
    return [b"ok"]
```

### Flask 示例

```python
from flask import Flask, request, abort
from hipi.webhook import verify_webhook_request

app = Flask(__name__)
SECRET = "your-shared-secret"

@app.post("/hipi/webhook")
def hipi_webhook():
    body = request.get_data()
    if not verify_webhook_request(SECRET, body, request.headers):
        abort(401)
    payload = request.get_json()
    print(payload["from"], payload["body"])
    return {"ok": True}
```

### Node.js 验签示例

```javascript
const crypto = require("crypto");

function verifyHiPiWebhook(secret, rawBody, timestamp, signature, maxAgeSec = 300) {
  const ts = Number(timestamp);
  if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > maxAgeSec) {
    return false;
  }
  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.${rawBody}`)
    .digest("hex");
  const provided = (signature || "").replace(/^sha256=/, "");
  return crypto.timingSafeEqual(
    Buffer.from(expected, "hex"),
    Buffer.from(provided, "hex")
  );
}
```

## 本地测试接收器

仓库附带简易测试脚本，可在局域网或本机验证转发与验签：

```bash
export HIPI_WEBHOOK_SECRET="test-secret"
python3 scripts/webhook-receiver.py --port 8765
```

在 HiPi「状态」页将 Webhook 设为 `http://<本机IP>:8765/`，并填入相同密钥，然后向模组 SIM 发送一条测试短信。

## 故障排除

- **401 / 验签失败**：确认密钥一致；使用原始 body 验签，勿先 `json.loads` 再 `json.dumps`
- **无请求到达**：检查 URL 可从 Orange Pi 访问；防火墙放行端口
- **时间戳过期**：同步系统时间（`timedatectl`）

更多模组与网络问题见 [故障排除](troubleshooting.md)。
