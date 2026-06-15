# DeepSeek 真实运行指南

本项目支持 DeepSeek / OpenAI-compatible API。仓库不会提交真实 API key，也不会伪造真实调用结果。

## 1. 配置 API key

推荐使用本地 `.env`，不要把 key 写进源码：

```bash
cp .env.example .env
# 编辑 .env，填入：DEEPSEEK_API_KEY=sk-your-real-key
```

Linux/macOS 也可以临时导出环境变量：

```bash
export DEEPSEEK_API_KEY="你的 key"
```

Windows PowerShell：

```powershell
$env:DEEPSEEK_API_KEY="你的 key"
```

## 2. 检查配置，不发起网络调用

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
```

你应该看到：

```json
{
  "model": "deepseek-v4-flash",
  "base_url": "https://api.deepseek.com",
  "api_key_configured": true,
  "api_key_source": "DEEPSEEK_API_KEY"
}
```

## 3. 先跑 smoke test

这一步只验证 API 连通性，不修改代码：

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-smoke --model deepseek-v4-flash
```

证据文件：

```text
runs_deepseek_smoke/deepseek_smoke.json
```

## 4. 发起真实 agent run

```bash
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_real_task.json \
  --mode api \
  --model deepseek-v4-flash \
  --allow-llm-calls \
  --runs runs_deepseek_real
```

## 5. 检查证据文件

运行后进入输出的 run 目录，重点检查：

```text
api_agent_run.json      # 每轮 LLM action、observation、token usage
trace.jsonl             # 全局执行链路
patch.diff              # 实际修改
test_result.json        # acceptance 输出
scorecard.json          # 质量评分
report.html             # 面试演示报告
context_summary.json    # 选入上下文的文件
```

## 6. 如何判断不是“假接入”

真实运行必须满足：

1. `api_agent_run.json` 存在。
2. `api_agent_run.json` 中 steps 数量大于 0。
3. `total_usage.prompt_tokens` 和 `completion_tokens` 大于 0。
4. `patch.diff` 由 agent 工具调用产生，而不是人工提前改好。
5. `test_result.json` 显示 acceptance 命令通过。

如果没有 API key，项目只能跑 local/scripted 模式或 api-check 占位模式。不能把 local 模式结果说成真实 DeepSeek 结果。


更多 key 安全说明见 `docs/secure_deepseek_key_setup.md`。
