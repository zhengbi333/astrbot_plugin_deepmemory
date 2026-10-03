# alpha-0.31（2026-08-08）

## 修复

- **读取运行时配置失败（Unexpected UTF-8 BOM）**：AStrBot 写入插件配置文件时带有 UTF-8 BOM 头，插件以 `utf-8` 解码导致 JSON 解析失败（配置读取被跳过）。所有配置文件读取统一改用 `utf-8-sig`（自动跳过 BOM；无 BOM 时行为等同 utf-8）。
