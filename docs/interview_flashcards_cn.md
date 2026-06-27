# OpenAgent Harness 面试闪卡

## 闪卡 1：项目一句话

问：OpenAgent Harness 是什么？

答：面向 Coding Agent 的本地执行与评测框架，让模型按 JSON action 调工具、改代码、跑测试，并生成 patch、trace、gate、scorecard 和 report。

## 闪卡 2：解决什么问题

问：它解决了什么问题？

答：解决“模型说修好了但无法证明”的问题。Harness 用 diff、测试、scope 检查、trace 和 scorecard 证明一次 Agent 修改是否真实、安全、可复盘。

## 闪卡 3：核心链路

问：一次 run 的链路是什么？

答：`task.json -> isolated workspace -> context/code index -> JSON action agent -> tool registry -> permission policy -> acceptance -> quality gate -> scorecard/report/trace`。

## 闪卡 4：task.json

问：`task.json` 里有什么？

答：repo、goal、allowlist、acceptance、budget。它定义任务目标、可改范围、验收命令和预算边界。

## 闪卡 5：为什么 JSON action

问：为什么不用自由文本？

答：JSON action 更结构化，工具名和参数清楚，能做权限检查和 trace 记录，也方便把 observation 回传给模型。

## 闪卡 6：有哪些工具

问：工具有哪些？

答：`read_file`、`search_repo`、`inspect_symbols`、`edit_file`、`write_file`、`run_command`。

## 闪卡 7：为什么 edit_file

问：为什么偏用 `edit_file`？

答：它要求 exact old_text/new_text 和 expected replacements，能避免整文件重写，减少无关 diff，让 patch 更可审计。

## 闪卡 8：怎么防越权

问：怎么防止改不该改的文件？

答：工具层用 `PermissionPolicy` 检查 allowlist，运行后 `QualityGate` 再根据 `patch.diff` 检查 changed paths。

## 闪卡 9：怎么防危险命令

问：怎么防止危险 shell？

答：`PermissionPolicy` 拦截 `rm -rf`、`git reset --hard`、`git push` 等危险模式，并限制命令前缀为测试/检查类命令。

## 闪卡 10：ContextBuilder

问：ContextBuilder 做什么？

答：扫描仓库、给文件打分、输出 repository map、symbol map、README/pyproject 和候选文件内容，减少上下文噪音。

## 闪卡 11：CodeIndex

问：AST symbol index 有什么用？

答：提取函数、类、行号和签名，让模型能用 `inspect_symbols` 定位代码结构，不只是 grep 文本。

## 闪卡 12：QualityGate

问：QualityGate 检查什么？

答：是否有 diff、是否跑测试、测试是否通过、是否在 allowlist 内、report 是否存在。

## 闪卡 13：Scorecard

问：Scorecard 为什么需要？

答：pass/fail 不够细。Scorecard 还看测试、scope、patch 行数、改动文件数和 timeout，用来比较不同 agent 的 patch 质量。

## 闪卡 14：Benchmark

问：benchmark 结果是什么？

答：toy benchmark `7/7 pass`，realistic benchmark `3/3 pass`，当前本机测试 `66 passed`。

## 闪卡 15：DeepSeek 模式

问：DeepSeek 接入怎么讲？

答：`llm.py` 实现 DeepSeek/OpenAI-compatible client；真实调用默认关闭，必须显式 `--allow-llm-calls`，避免误花钱。

## 闪卡 16：scripted baseline

问：scripted baseline 是不是写死答案？

答：它是为了无 key 稳定演示完整链路。项目核心是 runner、tool registry、policy、gate、trace、scorecard；API agent loop 也已接入。

## 闪卡 17：和 Platform 的关系

问：Harness 和 Platform Backend 怎么分工？

答：Harness 是执行面，负责工具调用、patch、测试、trace、scorecard；Platform 是控制面，负责 API、run 状态、worker、artifact 查询、限流和成本。

## 闪卡 18：不足

问：项目不足是什么？

答：还不是容器级沙箱，没有完整 SWE-bench，没有多候选并行，没有 tree-sitter 多语言索引。v1 目标是面试可跑、可讲、可审计。

## 闪卡 19：下一步

问：下一步怎么升级？

答：容器隔离、tree-sitter、hidden tests/mutation testing、多候选并行、artifact API、成本监控和人工 approve。

## 闪卡 20：个人收获

问：最大收获？

答：Agent 不是一次模型回答，而是工具、权限、上下文、执行、测试、证据和成本控制组成的工程系统。
