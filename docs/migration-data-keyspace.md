# 迁移数据契约与键空间（Task 2）

## 目标

将旧项目中账号池、博主池、去重集合、计数器、AI上下文统一为 JSON 契约，避免 TXT 作为运行时主存储。

## Keyspace

| 业务域 | keyspace | 主键建议 |
|---|---|---|
| 账号池 | `account_records` | `(device_index, username)` |
| 博主池 | `blogger_records` | `(ai_type, username)` |
| 去重集合 | `dedupe_records` | `(namespace, key)` |
| 计数器 | `counter_records` | `(namespace, key, date?)` |
| AI 上下文 | `ai_context_records` | `(device_index, ai_type)` |

## 示例结构

```json
{
  "account_records": [
    {
      "device_index": 1,
      "username": "u001",
      "password": "***",
      "twofa_secret": "BASE32",
      "status": "active",
      "tags": ["jp", "seed"]
    }
  ],
  "blogger_records": [
    {
      "username": "target_a",
      "ai_type": "volc",
      "source": "scrape",
      "bound_device": 1,
      "last_scraped_at": "2026-03-05T12:00:00Z",
      "cooling_until": "2026-03-05T14:00:00Z"
    }
  ],
  "dedupe_records": [
    {
      "namespace": "quote_user",
      "key": "@someone",
      "first_seen_at": "2026-03-05T12:00:00Z",
      "last_seen_at": "2026-03-05T12:00:00Z",
      "ttl_seconds": 86400
    }
  ],
  "counter_records": [
    {
      "namespace": "nurture_daily",
      "key": "device:1",
      "value": 3,
      "date": "2026-03-05",
      "updated_at": "2026-03-05T12:00:00Z"
    }
  ],
  "ai_context_records": [
    {
      "device_index": 1,
      "ai_type": "volc",
      "persona": "dating-friendly",
      "memory": ["prefers short replies"],
      "last_prompt": "...",
      "last_response": "...",
      "updated_at": "2026-03-05T12:00:00Z"
    }
  ]
}
```

## 幂等与冲突策略

- `account_records`：以 `(device_index, username)` upsert；后写覆盖敏感字段。  
- `blogger_records`：以 `(ai_type, username)` upsert；`cooling_until` 取更晚值。  
- `dedupe_records`：相同 `(namespace,key)` 仅更新时间戳，不重复插入。  
- `counter_records`：同键同日累加；跨日重置。  
- `ai_context_records`：同键覆盖 `last_prompt/last_response`，`memory` 限长（建议 50）。

## 无效载荷处理

- 缺少主键字段 → 拒绝写入。
- 字段类型错误（如 `value` 非 int）→ 拒绝写入。
- 未知 keyspace → 拒绝写入。

实现参考：`core/data_contracts.py`。
