# OpenAgent 边界探索记录 2026-06-23

## 目的

这次探索不是为了证明模型永远能修好代码，而是故意构造一个更接近后端工程的复杂任务，观察 OpenAgent Harness 在真实 DeepSeek 路径下的边界：

- 模型能否跨多个文件完成修复。
- JSON action loop 在长输出下是否稳定。
- acceptance test、allowlist、scorecard、artifact hygiene 是否能给出可解释证据。
- 哪些短期风险会影响面试可信度。

## 复杂任务设计

任务路径：

`custom_tasks/dpsk-complex-policy-pipeline-20260623/task.json`

任务包含 3 个可修改文件：

- `config_loader.py`：要求深合并 nested config，且不能污染 `DEFAULTS`。
- `policy_engine.py`：要求实现 suspended、rate limit、private read、locked write、admin override、anonymous limit 等规则优先级。
- `audit.py`：要求递归脱敏 `token/password/secret` 等字段，并保持 deterministic output。

原始状态：

```text
6 failed, 1 passed
```

DeepSeek 真实运行结果：

```text
run_id=dpsk-complex-policy-pipeline-20260623-4179b2ac
tests=7 passed
changed_files=3
patch_lines=118
total_tokens=48828
estimated_cost_usd=0.00829276
initial_gate_status=fail
initial_failure_type=ArtifactHygieneViolation
```

## 暴露的问题

### 1. Artifact hygiene 有误报风险

DeepSeek 修复后的业务测试全过，但 run 被判为 `ArtifactHygieneViolation`。根因不是模型泄露密钥，而是任务 id `dpsk-complex-policy-pipeline-20260623` 中包含 `sk-`，触发了 `sk-...` secret 正则。

已修复：

- `artifact_hygiene.py` 的 `sk-` 正则增加左边界，避免把普通 slug 中的 `sk-` 当作密钥。
- `tests/test_artifact_hygiene.py` 增加回归测试，确保 `dpsk-complex...` 不误报，但真实 `sk-live-secret-value` 仍会被抓。

### 2. Scorecard 对边界失败解释过于粗

修复前，测试通过、allowlist 正确、patch 有效，但 hygiene 失败会导致 score 变成 0。面试时这会被误解为“模型完全失败”。

已修复：

- `scoring.py` 保持 gate 失败，但保留工程证据分数。
- `tests/test_scoring.py` 增加回归测试，验证 hygiene 阻断的已验证 patch 仍有 partial credit。

### 3. JSON action loop 在复杂任务下会出现 invalid action

这次 run 中，DeepSeek 第 1 步和第 5 步输出过非法 JSON，但 agent loop 通过 observation 反馈继续执行，最后修复成功。

短期改进方向：

- 给 invalid JSON 增加更明确的 repair prompt。
- 记录 `invalid_action_count` 到 `scorecard.json` 或 `api_agent_run.json` 摘要。
- 对连续非法 JSON 设置失败类型，例如 `InvalidToolCallLoop`。

### 4. 复杂任务仍然不等于真实大型仓库任务

这次任务比单文件 toy benchmark 更强，但仍然是小型人工构造 repo。它能证明 Harness 的多文件修复、工具调用和证据链，不应被夸大成 SWE-bench 或真实生产代码库覆盖。

短期改进方向：

- 新增 1-2 个多文件 realistic benchmark，覆盖 service + config + tests。
- 为复杂任务建立独立 `api_realistic` 任务集，不和 zero-cost scripted baseline 混在一起。
- 保持 `benchmarks/` 做稳定回归，`custom_tasks/` 或 `api_realistic/` 做真实模型边界探索。

## 面试可讲版本

如果面试官问“你的项目会不会太 toy”，可以这样答：

> 早期 benchmark 的确偏小，所以我后来故意加入了一个多文件后端策略任务：配置深合并、权限规则优先级、审计脱敏。DeepSeek 在 Harness 里把业务测试从 6 败修到 7 过，说明执行链路能承载比单函数更复杂的任务。但更有价值的是，这次探索暴露了 artifact hygiene 的 false positive 和 scorecard 解释问题。我没有把失败藏起来，而是把它变成回归测试和评分修复。这个项目的重点不是宣称模型万能，而是把 Agent 执行过程变成可验证、可审计、可改进的后端系统。

如果面试官追问“真实模型失败怎么办”，可以这样答：

> 我把失败分层看：如果 pytest fail，是任务修复失败；如果 provider 401/502，是模型服务或 key 问题；如果 gate fail 但 tests pass，可能是 scope 或 artifact hygiene 问题。这次复杂任务就是 tests pass 但 hygiene false positive，我修了扫描边界并保留了回归测试。这样系统不会只给一个模糊的 fail，而是能定位到具体工程边界。

如果面试官追问“下一步怎么提升”，优先级是：

1. 增加 schema-constrained tool call / JSON repair，减少 invalid action。
2. 建立 `api_realistic` 多文件任务集，专门测真实模型能力。
3. 让 scorecard 区分 `gate_status` 和 `engineering_score`。
4. 做容器级沙箱或更强的进程隔离，替代当前的 workspace + policy 约束。
5. 更新公开 release，移除运行产物、旧 zip、db、logs，保留最小可复现证据。
