# alpha-0.95

## P1-10：把「注入了哪几条记忆」读出来

查证后省了很多工作：`injection_logs` 表**早就在记录**这些：

```sql
created_at, session_id, scope, query,
selected_memory_ids,   -- 命中了哪几条
blocked, injection_chars
```

`service.py:2488` 一直在写，开关 `injection.enable_injection_logs` 默认 True。
**数据早就有，只是没有接口读出来。**

## 本轮加 `bridge.recent_injections(limit)`

返回：

```python
[{created_at, session_id, query, chars,
  items: [{id, summary}]}]
```

- 把 `selected_memory_ids` 解析成 id 列表，再逐条查 `get_memory` 补上摘要；
- 摘要取 `summary`，空的就用 `content` 前 80 字。

## 测试抓到一个真 bug

`selected_memory_ids` 存的是 **JSON 数组字符串** `'["m1","m2"]'`，
我第一版按逗号切，得到的是 `['["m1"', '"m2"]']` —— **id 全带引号和括号**，
拿去查 `get_memory` 必然查不到（面板上会显示 "关于 ["m1 的记忆" 这种鬼东西）。

已改成：**先 JSON 解析**，失败才退回逗号切 + 正则清洗（兼容老数据）。
