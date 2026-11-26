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

## 快速开始

```bash
uv sync
```

```bash
uv run uvicorn p1_fc_agent.app:app --port 8000
```

另开一个终端，问 Agent 一个问题。`-N` 关掉 curl 的缓冲，才能看到事件逐条到达：

```bash
curl -N -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d '{"question":"北京和上海今天的气温相差多少度？"}'
```

Agent 每走一步，就推一条 SSE 事件：`step`（Thought + Action）、`observation`（工具结果）、`final`（最终答案），最后一条 `done` 表示流结束。

## 接口一览

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | /health | 健康检查 |
| POST | /echo | 原样回话（W2-S1） |
| GET | /tools/{tool_name} | 查工具的参数 Schema（W2-S2） |
| POST | /calculator | 四则运算，需要请求头 `X-API-Key`（W2-S2） |
| POST | /stream | 把一段文字逐字推流（W2-S3） |
| POST | /ask | ReAct Agent：流式返回每一步 Thought/Action/Observation（W2 周末） |

## 测试

```bash
uv run pytest
```