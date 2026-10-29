# 第三方代码与来源

- `src/agent_foundation/`：来自同级 `agent-foundation` 仓库的提交 `f121e7e792c7b9d107dda10222b3af1a465c9057`。本地副本与该提交的七个 Python 源文件一致；该仓库附有 Copyright (c) 2026 aninstein 的 MIT 许可证。本仓库根目录保留相同许可证。公开发布前仍须由代码权利人确认该仓库及其代码可公开分发；本次审计无法从未登录的 GitHub 页面验证其公开状态。
- `vendor/deerflow/`：来自 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 的提交 `e9074b7126833b5ca4739bcedcbbed01b211246c`。两个压缩包各自包含原项目的 MIT `UPSTREAM_LICENSE`，版权归 Bytedance Ltd. 和 DeerFlow Authors。压缩包的 SHA-256 记录在 `vendor/deerflow/provenance.json`。

`financial-freedom` 只用作产品规模参照，没有作为代码依赖纳入本仓库。项目依赖的 Python 包由 `pyproject.toml` 声明，安装时还需遵守各包自身的许可证。
