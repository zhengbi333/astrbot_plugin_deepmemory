# alpha-0.22（2026-08-08）

## 修复（重要）

- **设置保存不生效的真正根因：配置文件路径错了一层**：
  - 对照范例插件（astrbot_plugin_memory_companion）的 `_plugin_config_path`：`data_dir.parent.parent`（向上两级），而本插件写成了 `data_dir.parent`（一级）——导致插件始终读写 `data/plugin_data/config/astrbot_plugin_deepmemory_config.json`（错误位置），而 AstrBot 配置系统读写的是 `data/config/astrbot_plugin_deepmemory_config.json`（正确位置）。两个文件长期分裂，配置自然"保存了却像没保存"。
  - 本机已核实：正确位置文件 `embedding_enabled: true`，错误位置文件 `embedding_enabled: false`（旧值），与 UI 显示"关"完全吻合。
  - 修复：`_config_file_path` 对齐范例（向上两级）；已删除错误位置的残留配置文件。
- **设置页新增「配置诊断」卡片**：显示配置文件路径、文件是否存在、磁盘中的 `embedding_enabled` 与插件实际读取值，以及两者是否一致——若再异常可直接看到是哪一环。

## 说明

- 修复后插件与 AstrBot 配置系统读写同一文件，WebUI 设置页与 AstrBot 插件配置页完全同步。
- 保存仍失败时，页面会明确提示"写入磁盘失败"，日志出现 `保存主配置文件失败`（此时自动回退插件数据目录的备用配置文件 `runtime_config.json`，不影响持久化）。
