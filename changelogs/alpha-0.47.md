# alpha-0.47（2026-08-08）

## 修复

- **二氧化硫爆炸不可见**：
  - 根因：卡片 hover 的 `glow-pulse` 动画会覆盖同元素的 `melt` 融化动画（同一元素同一时刻只能播放一个 animation），点击后鼠标悬停在卡片上导致融化被覆盖。
  - 修复：融化动画改为 `!important` 强制生效；爆炸期间给 body 加 `exploding` 状态并**全局禁用交互**（pointer-events: none），避免 hover/点击干扰融化与变红效果。
- **DS 卡片名字鬼畜**：人物卡名称与简介改为不换行（nowrap + 省略号），抖动时行宽变化不再引发重排鬼畜。

## 其他

- 版本备份：`工作区 backup 目录下的 astrbot_plugin_deepmemory_alpha-0.47\`。
