# alpha-0.93

## 修：platform 口径不一致导致跨插件记忆被静默挡掉

### 问题（由上一版 0.92 新增的平台隔离暴露出）

0.92 给 `visibility_filter` 加了平台隔离检查：

```python
if record.platform and record.platform != ctx.platform:
    return False, "platform_isolation"
```

**检查方向是对的，但两侧写入的 platform 值本来就不一样**：

| 写入方 | 取值来源 | 实际值 |
|---|---|---|
| deepmemory 自己 | `event.get_platform_name()`（AstrBot 定义为**适配器类型**） | `aiocqhttp` |
| storyteller | `unified_msg_origin` 的**会话前缀**（平台**实例标识**） | `阡墨` |

于是同一会话出现两种写法（真实库里就是这么存的：`memories` 的身份记忆是 `aiocqhttp`，
而 `timeline` 里同一轮对话的 bot 行是 `阡墨`），严格相等一比对，
**跨插件读到的记忆就被静默挡掉**。实测（真实库快照 + 真实函数）：

```
resolve_event_context(event).platform = 'aiocqhttp'      ← deepmemory 写入口径
build_session_context(event)['platform'] = '阡墨'         ← storyteller 口径
→ 用 0.92 的 visibility_filter 判定：identity 记忆在 storyteller 上下文下 被挡 ✗ (platform_isolation)
```

另外 AstrBot 自己的注释点明了更根本的问题：

> `def get_platform_name(self): """获取这个事件所属的平台的**类型**…
> NOTE: 用户可能会同时运行多个相同类型的平台适配器。"""`

—— 用**类型**做隔离，两个同类实例（比如两个 QQ 号）会互相看见，**隔离其实没生效**；
却会把按实例名读写的调用方挡在外面。

### 修复（只动 deepmemory 一侧，storyteller 本来就是实例标识）

1. **写入口径统一为「平台实例标识」**（会话前缀，也就是 `unified_msg_origin` 的第一段）：
   `resolve_event_context` 前缀优先，只在拿不到前缀时才退回适配器类型。
   这样既与 storyteller 一致，也**真正能区分同类型的多个实例**。
2. **一次性迁移**（`SCHEMA_VERSION` 1→2，成功才升版本、失败下次重试；幂等）：
   - `memories` / `timeline`：`platform` 归一为各自 `session_id` 的前缀；
   - `users`：`platform` 同步归一，`user_key` 由 `类型:用户` 改写为 `实例:用户`
     （主键改写前先查碰撞：目标键已存在则**合并**并保留已有的人格绑定，不报错）；
   - 第二遍：**没有 `session_id` 的行**（面板手动创建的记忆常见）按 `user_id` 用 `users` 表回填。
3. **不放宽比较**：`visibility_filter` 保持严格相等。
   理由——上游即使不传 platform，`SessionContext.from_dict` 也会经 `normalize_session_fields`
   **从会话前缀推导**出实例标识（已加用例 G1/G2 固化这一点），所以"上下文没有平台"不是真实场景；
   放宽比较只会让未知上下文读到别的平台的记忆。**隔离强度不降**。

### 验证（`_st_test/audit_57_platform_canonical.py`，全程在真实库只读快照上做）

| 用例 | 结果 |
|---|---|
| 迁移：memories / timeline / users 全部归一为实例标识，人格绑定不丢 | ✓ |
| 迁移幂等（重复执行结果不变） | ✓ |
| 端到端：迁移后 identity / promise 记忆在 **storyteller 上下文**下可见（原故障消除） | ✓ |
| `resolve_event_context` 返回实例标识 | ✓ |
| 严格隔离仍生效：真跨平台（阡墨 ↔ webchat）被拦；**上一版新增的 ownerless 检查未被我改松** | ✓ |
| users 主键碰撞时合并而非报错 | ✓ |
| 无 session_id 的面板记忆按用户回填后可见 | ✓ |
| G1/G2/G3：`from_dict` 自动推导平台 → "未传平台"的调用方仍可见本平台、且仍能隔离他平台 | ✓ |

合计 **21/21**；另跑：我的 deepmemory 探针 **146/146**、storyteller 26 批回归 **541/541**、
上一版新增的 `test_deepmemory_regressions.py` **OK**（其"平台不一致即拦截"的语义保持不变）。

### 本轮我自己的两处失误（已修）

1. 迁移里 `users` 的新 platform 一开始从**旧 user_key** 推导（`aiocqhttp:…` → `aiocqhttp`），
   与旧值相同 → 被跳过；改为从该用户**会话前缀**推导。
2. 一度把比较改成"双方都非空才比"（想容忍历史残留），这会**削弱隔离**；
   已回退为严格相等 —— 残留由迁移解决，不靠放宽比较兜底。
