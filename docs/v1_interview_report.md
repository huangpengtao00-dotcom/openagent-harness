# OpenAgent Harness v1.0 面试交付报告

## 一句话定位

OpenAgent Harness 是一个低成本 Coding Agent 评测与执行平台，用 DeepSeek / OpenAI-compatible LLM 在受控工具与权限边界内完成代码修复，并输出可审计的 trace、patch、test result、scorecard 和 HTML report。

这个项目不要包装成某个商业工具的复刻。更稳的表述是：它实现了 coding agent 的核心工程闭环：上下文选择、工具调用、局部 patch、权限检查、测试验收、成本记录与报告审计。

## v1.0 已落地能力

1. JSON-action agent loop：模型每轮只能输出一个 JSON action。
2. Tool registry：工具通过注册层暴露，包括 search_repo、inspect_symbols、read_file、edit_file、run_command、finish。
3. Patch-level edit：优先 old_text -> new_text 精确替换，避免整文件覆盖。
4. Permission policy：写文件必须在 allowlist 内，命令需要通过安全检查。
5. Context compaction：根据任务目标选择高相关文件，记录 context_summary.json。
6. AST symbol index：用 Python AST 抽取函数、类、签名与行号。
7. Acceptance verification：每个任务用 task.json 内的 acceptance 命令验收。
8. Scorecard：不只 pass/fail，还计算 patch 大小、scope、安全、timeout 等维度。
9. HTML report：展示 Task Goal、Selected Context、Tool Calls、Permission Decisions、Patch Diff、Test Output、Cost Estimate、Failure Analysis。
10. Realistic benchmarks：新增 3 个接近真实 issue 的任务，区别于玩具示例。

## 面试演示路径

```bash
python -m pytest tests/test_v1_interview_delivery.py -q
PYTHONPATH=src python -m openagent_harness.cli eval --benchmarks benchmarks_realistic --runs runs_v1_realistic
```

打开：

```text
runs_v1_realistic/eval_report.html
```

任选一个 run 目录打开：

```text
report.html
patch.diff
test_result.json
scorecard.json
context_summary.json
trace.jsonl
```

## 面试官最可能追问

### 1. 这和普通自动化测试工具有什么区别？

普通测试工具只执行测试。OpenAgent Harness 的对象是 coding agent：它要先构造上下文，再让 LLM 通过工具读代码、查符号、局部编辑、跑测试，并把整个决策过程记录下来。这里评估的不只是代码是否通过测试，还包括修改范围、工具调用是否安全、成本是否可控、过程是否可审计。

### 2. 为什么要 allowlist？

Coding agent 容易越权修改无关文件，甚至通过命令破坏环境。allowlist 把任务边界显式写进 task.json，policy 层统一检查读写和命令，HTML report 里也能展示权限决策。这个设计让 agent 行为从“相信模型”变成“模型只能在边界内执行”。

### 3. 为什么不用整文件覆盖？

整文件覆盖容易引入格式变化、删除注释、误伤无关逻辑。v1.0 优先使用 edit_file 的精确替换：old_text 必须唯一匹配，否则拒绝执行。这降低了幻觉 patch 风险，也便于 code review。

### 4. 为什么 benchmark 要 realistic？

早期 toy benchmark 可以验证框架，但面试时说服力不足。v1.0 新增了 429 retry、嵌套配置合并、API 错误泄露三个真实工程风格任务，task goal 按 issue 形式写，acceptance 用 pytest 验收，allowlist 限制可改文件。

### 5. DeepSeek 接入的价值是什么？

国内低成本 AI 工程落地不能默认依赖昂贵模型。这个项目把模型层抽象为 OpenAI-compatible client，可以接 DeepSeek，也可以接其他兼容服务。重点不是模型名，而是：低成本模型在受控工具、上下文压缩和测试反馈下能否稳定完成代码修复。

## 当前边界

1. 还不是完整 SWE-bench 级系统。
2. 没有做真正的容器沙箱，只是 workspace 隔离和 policy 约束。
3. 多 agent 并行只是 portfolio 雏形，不建议面试时夸大。
4. 真实 DeepSeek 运行需要用户自己的 API key，本仓库不会伪造线上调用结果。

## 最稳简历写法

设计并实现低成本 Coding Agent Harness，支持 DeepSeek/OpenAI-compatible LLM 接入、JSON tool-call agent loop、工具注册、AST 代码索引、上下文压缩、allowlist 权限策略、局部 patch 编辑、acceptance verification、token/cost 统计与 HTML trace report，用于评估 coding agent 在代码修复任务中的有效性、成本与安全边界。
