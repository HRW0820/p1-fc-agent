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

## 配置模型 key

第一次运行前，在仓库根目录新建 `.env`，写一行 `DEEPSEEK_API_KEY=你的key`。这个文件已在 `.gitignore` 里，不会被提交。

## 快速开始

```bash
uv sync
```

```bash
uv run uvicorn p1_fc_agent.app:app --port 8000
```

另开一个终端，问 Agent 一个问题。`-N` 关掉 curl 的缓冲，才能看到事件逐条到达；`X-API-Key` 是 W2-S2 的查卡，key 读的是环境变量 `P1_API_KEY`，没设时默认是 `dev-key`：

```bash
curl -N -X POST http://127.0.0.1:8000/ask -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{"question":"北京和上海今天的气温相差多少度？"}'
```

Agent 每走一步，就推一条 SSE 事件：`step`（Thought + Action）、`observation`（工具结果）、`final`（最终答案）。中途出错会推一条 `error`，最后一条 `done` 表示流结束。

## 接口一览

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | /health | 健康检查 |
| POST | /echo | 原样回话（W2-S1） |
| GET | /tools/{tool_name} | 查工具的参数 Schema（W2-S2） |
| POST | /calculator | 四则运算，需要请求头 `X-API-Key`（W2-S2） |
| POST | /stream | 把一段文字逐字推流（W2-S3） |
| POST | /ask | ReAct Agent：流式返回每一步 Thought/Action/Observation（W2 周末），需要请求头 X-API-Key（W3）。 |

## 真模型调用（W3）

`src/p1_fc_agent/llm.py` 是调 DeepSeek 的最小封装：`load_api_key()` 读 key，`chat(messages)` 发一段对话并返回 `(回复, 用量, finish_reason, tool_calls)`，`cost(usage)` 按空闲时段单价算出这次调用花了多少元。单价来自 DeepSeek 官方价格页，高峰时段（工作日 9-12 点、14-18 点）是两倍。

`calling.py` 是 Function Calling 的核心：`tool_spec` 把表格写成说明书，`decide` 让模型挑表，`ask` 走完一轮（挑表 → 执行 → 回传 → 总结）。

`tools.py` 的三张表格就是模型看到的工具说明书：类文档字符串是工具描述，`Field(description=…)` 是每个参数的说明；`WeatherQuery` 和 `PopulationQuery` 共用表头 `CityForm`，`unit` 是可选的枚举（`celsius` / `fahrenheit`）；`calling.run` 查的是假账本（天气、人口），查不到回「未知城市」。

`fc_loop.py` 是 FC 版 ReAct 循环：`execute` 执行一张卡，`react_events` 一轮一轮问模型、把它递的每张卡执行完再递回去，`run_react` 只要最后那句回答。`react_events` 还收一个 `temperature`（默认 0.0）和一个 `budget`（可以不传）。

`budget.py` 是单次会话的账本：`Budget(limit_yuan=…)` 每打完一次电话 `charge(usage)` 记一笔（次数、输入输出 token、花了多少元），`report()` 出账单；累计超过上限时 `charge` 抛 `OverBudget`。`fc_loop.react_events` 接了账本以后，钱超了就不再打下一次电话：模型这次还要用工具就停，用账单代替答案；这次已经给出答案就照常交付。上限是打完电话才检查的，所以最多会超一次电话的钱。单价默认是空闲时段的，高峰时段要传翻倍的 `price`。

`experiments/w3_compare.py` 是 W3 的对照实验脚本：同一个问题分别跑文本协议（`react_loop` + 真模型大脑）和 Function Calling（`fc_loop`），各跑 10 遍，比 `temperature=0` 和 `0.7`。真调模型，结果在同目录的三个 `w3_compare_results*.json` 里，报告见《W3-对照实验报告.md》。

结构化输出在 `src/p1_fc_agent/structured.py`：`ask_json(messages, 表格)` 让模型按一张 Pydantic 表格回答（打开 JSON 模式），`parse(text, 表格)` 把回答变成对象。回答不是 JSON、表格没填对、话说一半被掐断，都报 `ParseError`，报错信息是一句能照着做的话。

## 测试

```bash
uv run pytest
```