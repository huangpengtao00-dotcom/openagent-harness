# DeepSeek Key 安全接入说明

不要把真实 API key 写进源码、README、task.json、测试文件或提交记录。项目只从本机环境变量或本地 `.env` 文件读取 key。

## 推荐方式：本地 `.env`

复制模板：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-your-real-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

`.gitignore` 已经排除 `.env` 和 `.env.*`，只保留 `.env.example`。打包或提交前仍建议手动检查：

```bash
git status --short
```

## 配置检查：不发起网络调用

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-check --model deepseek-v4-flash
```

输出只会显示：

```json
{
  "api_key_configured": true,
  "api_key_source": "DEEPSEEK_API_KEY"
}
```

不会打印真实 key。

## 真实 API smoke test

这一步会真实扣少量 token，只验证连接，不修改代码：

```bash
PYTHONPATH=src python -m openagent_harness.cli deepseek-smoke --model deepseek-v4-flash
```

输出证据在：

```text
runs_deepseek_smoke/deepseek_smoke.json
```

该文件包含模型响应和 usage，但不包含 API key。

## 真实 agent run

```bash
PYTHONPATH=src python -m openagent_harness.cli run examples/deepseek_real_task.json \
  --mode api \
  --model deepseek-v4-flash \
  --allow-llm-calls \
  --runs runs_deepseek_real
```

API 调用默认关闭，必须显式加 `--allow-llm-calls`，避免误扣费。

## 面试说法

可以说：

> 项目没有把 key 写入配置文件或日志，而是通过本机环境变量 / `.env` 注入。CLI 的 `deepseek-check` 只验证配置状态，`deepseek-smoke` 负责一次真实 API 连通性验证，所有 run artifacts 只保存 usage、trace、tool calls 和 patch，不保存密钥。

不要说：

> 我把 key 放在项目里方便调用。
