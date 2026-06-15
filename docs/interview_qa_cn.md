# 面试问答速记

## Q1：你这个项目最核心的技术点是什么？

不是单个功能，而是 coding agent 的闭环工程化：上下文选择、JSON action 工具调用、权限约束、局部 patch、测试验收、trace 记录、scorecard 和 HTML 报告。

## Q2：这个项目和成熟 Coding Agent 工具有何关系？

参考的是通用工程模式，不是复刻产品。Coding Agent 的关键是 tool use、permission、context、trace。我在项目里实现了简化版：LocalToolRegistry、PermissionPolicy、ContextBuilder、JsonActionCodingAgent 和 report.html。

## Q3：DeepSeek 接入在哪里？

`llm.py` 里实现 OpenAI-compatible client；`model_adapter.py` 把 client 接入 agent loop；CLI 支持 `--mode api --model deepseek-v4-flash --allow-llm-calls`。真实运行需要 `DEEPSEEK_API_KEY`。

## Q4：为什么要做 scorecard？

只看 pass/fail 会掩盖问题。一个 patch 可能测试通过但改了很多无关文件，或者有 timeout 风险。scorecard 同时看 gate、测试、scope、patch 大小和 timeout，更适合评估 agent 行为质量。

## Q5：如果 LLM 输出非法 JSON 怎么办？

agent loop 会尝试从输出中解析 JSON 对象；失败时返回 invalid action，作为 observation 继续进入下一轮。更严格的做法是接 schema validator，这是后续可扩展点。

## Q6：如果 agent 修改了测试文件怎么办？

QualityGate 会根据 patch.diff 的 changed paths 和 task allowlist 比较，越权会标记 ScopeViolation。工具层也会在写入前用 PermissionPolicy 拦截。

## Q7：这个项目还有什么不足？

当前没有真正容器级沙箱，没有完整 SWE-bench 接入，没有并行多策略搜索，也没有语言服务器级别的跨文件语义索引。v1.0 的目标是面试可讲、可跑、可审计，而不是短期复刻成熟商业产品。

## Q8：下一步怎么提升？

优先顺序：真实 DeepSeek run 证据、更多 realistic benchmark、容器沙箱、schema-constrained tool call、多候选并行和失败原因分类。不要先做花哨 UI 或空泛多 agent。
