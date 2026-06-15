# 系统设计说明

## 架构分层

```text
TaskSpec(task.json)
  ↓
WorkspaceManager：复制隔离工作区
  ↓
ContextBuilder：repo map / symbol map / candidate files
  ↓
JsonActionCodingAgent：LLM 生成 JSON action
  ↓
LocalToolRegistry：工具注册与分发
  ↓
PermissionPolicy：读写/命令边界检查
  ↓
Acceptance：pytest 或自定义命令
  ↓
QualityGate + Scorecard + HTML Report
```

## 核心 trade-off

### 1. 低成本 LLM vs 高成功率

便宜模型适合批量评测，但单次成功率不一定稳定。项目通过 context compaction、工具约束、测试反馈和重试循环提升可用性，而不是只依赖模型能力。

### 2. 局部 patch vs 整文件重写

局部 patch 更安全，但要求 old_text 唯一匹配；整文件重写更简单，但误伤风险大。v1.0 默认建议 edit_file，write_file 作为兜底。

### 3. Toy benchmark vs realistic benchmark

Toy benchmark 用于快速回归，realistic benchmark 用于面试证明。v1.0 同时保留两类：`benchmarks/` 做稳定回归，`benchmarks_realistic/` 做工程说服力。

### 4. Policy 约束 vs Agent 自主性

限制越严格，agent 自由度越低；限制越松，安全风险越高。v1.0 用 allowlist 和危险命令拦截做最低成本的安全边界。

## 为什么这是 AI 工程项目

这个项目的核心问题不是“写一个 pytest runner”，而是如何把 LLM 放进真实软件工程闭环：模型输出不可信，必须通过工具协议、上下文管理、权限控制、测试验收、成本估算和可审计报告来工程化约束。
