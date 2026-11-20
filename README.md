# p1-fc-agent

> P1 阶段项目：不依赖框架，徒手交付一个**真模型的 Function Calling Agent**（M1 里程碑）。

## 目标（M1 验收形态）

- 裸调 OpenAI 兼容 API + 原生 Function Calling（tool_calls）
- FastAPI 服务壳，`/ask` 接口 SSE 流式返回每步 Thought/Action/Observation
- 3 个工具（天气/计算器/人口），支持并行工具调用
- 工具失败 → 错误转 Observation → 模型自纠错
- 单会话 token 成本上限（保险丝）

## 目录结构（随 W1-W4 逐步填充）

```
p1-fc-agent/
├── src/            # 领域代码（W1 起分层）
├── tests/          # pytest 测试（W2 起）
├── w1_concurrency_lab.py   # W1 并发实验
├── 03_function_calling.py  # W3 FC 版 Agent
└── pitfalls.md     # 踩坑日志（面试弹药库）
```

## 安全约定

- API key 一律放 `.env`，**绝不进仓库**（`.gitignore` 已配置）
- 提交前自查 `git diff` 里有没有密钥

## 快速开始（W1 填充）

```bash
uv sync
uv run python ...
```
