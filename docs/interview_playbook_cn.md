# 面试讲法：OpenAgent Harness 最终版

## 30 秒版本

我做的是一个面向 Coding Agent 的本地评测与执行 Harness。它不是简单封装 DeepSeek API，而是实现了 Coding Agent 的核心闭环：模型根据仓库上下文输出 JSON action，系统通过工具注册层执行 read/search/symbol-index/edit/test，再把 observation 回传给模型迭代。外围加了 allowlist 权限控制、危险命令拦截、patch 级编辑、benchmark 评测、quality gate、scorecard 和 HTML trace 报告，用来评估 agent 是否真的修复了代码且没有越权。

## 2 分钟版本

这个项目的核心问题是：大模型生成代码很容易，但如何判断它真的能作为工程 agent 安全、稳定地修改仓库？

所以我把系统拆成了五层：

1. **任务层**：`task.json` 定义 repo、goal、allowlist、acceptance、budget。
2. **上下文层**：扫描 repo，构造 repository map，并用 Python AST 抽取函数/类符号，做 context compaction。
3. **Agent 层**：DeepSeek/OpenAI-compatible LLM 必须按 JSON action 调工具，不能自由执行 shell。
4. **工具与安全层**：工具注册包括 `read_file`、`edit_file`、`search_repo`、`inspect_symbols`、`run_command`；写入必须在 allowlist 内，危险命令会被拦截。
5. **评测层**：隔离 workspace 里运行 acceptance，生成 `patch.diff`、`test_result.json`、`gate.json`、`scorecard.json`、`report.html` 和 `trace.sqlite`。

我的重点不是追求“模型回答得漂亮”，而是工程上可观测、可复现、可审计。

## 面试官可能追问

### Q1：你这个和普通 AutoGPT / LangChain demo 有什么区别？

普通 demo 很多只展示能调用工具，但没有严格评测闭环。我的项目强调三点：一是 patch 必须真实落盘并生成 diff；二是必须通过 acceptance；三是 scope violation、regression、no patch、unverified 都会被 quality gate 分类。这更接近工程平台，而不是 prompt demo。

### Q2：为什么要接 DeepSeek？

国内面试环境下，DeepSeek 成本低、接入方便，适合做大量 coding-agent benchmark 实验。项目里 API 层做成 OpenAI-compatible，所以后续可以替换成 Qwen、Kimi、GLM 或公司内部模型。模型只是 backend，核心壁垒在 harness 和 eval。

### Q3：为什么要做 AST symbol index？

单纯关键词搜索不理解代码结构。AST index 可以抽取函数、类、行号和签名，给模型更稳定的 repo map，也能支持 `inspect_symbols` 工具。后续可以换成 tree-sitter 支持多语言。

### Q4：为什么 edit_file 比 write_file 更好？

`write_file` 容易导致整文件重写，diff 很吵，也容易引入无关改动。`edit_file` 要求 exact old_text/new_text，并且检查替换次数。如果匹配 0 次或多次会失败，降低幻觉编辑风险。

### Q5：怎么证明不是“你写死 benchmark 答案”？

当前 scripted agent 只是离线演示路径，真正的 API 模式已经接好 DeepSeek/OpenAI-compatible client 和 JSON action loop。离线路径的作用是保证项目没有 API key 也能被面试官跑起来。重点评估逻辑、trace、gate、tool registry、policy 都是通用的。

### Q6：如果要做成公司内部平台，下一步是什么？

我会优先做四件事：

1. git worktree 隔离多候选，支持并行 agent sampling；
2. tree-sitter + embedding 混合代码检索；
3. mutation testing / hidden tests，避免 agent 只过公开测试；
4. Web UI 展示 trace、patch、scorecard，支持人工 approve。

## 简历写法

OpenAgent Harness：面向 Coding Agent 的本地评测与执行平台。设计并实现 DeepSeek/OpenAI-compatible LLM 接入、JSON-action agent loop、工具注册层、allowlist 权限策略、patch-level edit、AST symbol index、acceptance verification、trace replay、HTML scorecard report 与 benchmark evaluation，用于评估代码修复 Agent 的真实工程能力与安全边界。

## 你需要熟练掌握的代码文件

- `agent_loop.py`：模型-工具-观察循环。
- `tool_registry.py`：工具注册和执行。
- `policy.py`：权限边界和危险命令拦截。
- `context.py` / `code_index.py`：仓库上下文和符号索引。
- `runner.py`：workspace、diff、acceptance、gate、report 主流程。
- `gate.py` / `scoring.py`：评测标准。
- `llm.py`：DeepSeek/OpenAI-compatible API 客户端。
