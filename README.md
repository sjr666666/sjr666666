<div align="center">

# 石敬荣 · sjr666666

**Agent 开发 · 后端 / 全栈** · 2028 届本科在读

[![Merged PRs](https://img.shields.io/badge/Merged%20PRs-7-8250DF?style=flat-square&logo=git&logoColor=white)](https://github.com/sjr666666/sjr666666)
[![Upstream repos](https://img.shields.io/badge/Upstream%20repos-9-1F6FEB?style=flat-square&logo=github&logoColor=white)](https://github.com/sjr666666?tab=repositories)

</div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/merged-prs-dark.svg">
  <img src="./assets/merged-prs-light.svg" width="100%" alt="已合并的 Pull Request 总览">
</picture>

---

## 已合并的开源贡献

4 个 PR 合并进 [`helsome/folio`](https://github.com/helsome/folio)，围绕同一条线推进：先定下
**Stream Event Protocol v1** 的类型契约（依 ADR 0001），再给 `RunManager` 加上并行事件通道，
接着打通传输链路与渲染日志，最后把事件日志持久化 —— 进程重启后仍能重放。

<!-- STATS:BEGIN -->
**7** 个 PR 已被合并（2026 年）

- **4** 个合并进他人仓库（[`helsome/folio`](https://github.com/helsome/folio)）· 合计 **+4,015 / −46** 行 · 62 个文件
- **3** 个自有项目（`ai-elderly-health-assistant`）的发布与加固 PR

| 仓库 | PR | 变更内容 | 规模 | 交付周期 | 合并日期 |
|:--|--:|:--|--:|--:|--:|
| [`folio`](https://github.com/helsome/folio) | [#41](https://github.com/helsome/folio/pull/41) | feat(core): add Stream Event Protocol v1 types (ADR 0001) | `+233` · 4 文件 | 7 天 | 09-18 |
| [`folio`](https://github.com/helsome/folio) | [#42](https://github.com/helsome/folio/pull/42) | feat(shared): add parallel Stream Event v1 channel to RunManager | `+437` · 7 文件 | 7 天 | 09-18 |
| [`folio`](https://github.com/helsome/folio) | [#43](https://github.com/helsome/folio/pull/43) | feat: wire Stream Event v1 transport and renderer log | `+1,459` `−23` · 24 文件 | 7 天 | 09-18 |
| [`folio`](https://github.com/helsome/folio) | [#76](https://github.com/helsome/folio/pull/76) | feat(shared): persist stream event log for cross-restart replay | `+1,886` `−23` · 27 文件 | 6.7 天 | 09-18 |
| [`ai-elderly-health-assistant`](https://github.com/sjr666666/ai-elderly-health-assistant) | [#3](https://github.com/sjr666666/ai-elderly-health-assistant/pull/3) | fix(auth): improve login and registration validation | `+72` `−71` · 10 文件 | 2 分钟 | 08-05 |
| [`ai-elderly-health-assistant`](https://github.com/sjr666666/ai-elderly-health-assistant) | [#2](https://github.com/sjr666666/ai-elderly-health-assistant/pull/2) | Codex/publish project | `+32,520` `−7,445` · 219 文件 | 22 分钟 | 08-03 |
| [`ai-elderly-health-assistant`](https://github.com/sjr666666/ai-elderly-health-assistant) | [#1](https://github.com/sjr666666/ai-elderly-health-assistant/pull/1) | [codex] harden and document medication manager | `+507` `−561` · 29 文件 | 1.3 小时 | 08-01 |

<sub>由 [`scripts/generate_stats.py`](./scripts/generate_stats.py) 直连 GitHub REST API 生成，经 GitHub Actions 每日自动刷新 · 最后更新 2026-09-30 04:22 UTC</sub>
<!-- STATS:END -->

---

## 代表项目

**AI 药管家** —— 面向老年人的智能用药安全与健康管理应用：用药冲突检测 · AI 健康咨询 · 服药提醒 · 家属远程监护。

[仓库](https://github.com/sjr666666/ai-elderly-health-assistant) · MIT · ★ 7 · `Java 21` `Spring Boot` `MyBatis-Plus` `React` `MySQL` `Redis` `Docker`

工程化交付：[发布上线改造](https://github.com/sjr666666/ai-elderly-health-assistant/pull/2) · [登录注册校验加固](https://github.com/sjr666666/ai-elderly-health-assistant/pull/3) · [药品管理模块加固与补文档](https://github.com/sjr666666/ai-elderly-health-assistant/pull/1)
