"""W2-S4：把 01_minimal_loop.py 的同步 ReAct 循环改成异步版。"""

import asyncio
import re
from dataclasses import dataclass

from p1_fc_agent.tools import run_calculator

MAX_STEPS = 8                           # 保险丝：最多走几步（和 01 相同）

@dataclass
class RunResult:
    answer: str
    events: list[dict]

async def get_weather(city: str) -> str:
    await asyncio.sleep(0.05)            # 模拟一次网络请求
    fake_weather_db = {"北京": "12", "上海": "20", "广州": "25"}
    return fake_weather_db.get(city, f"未知城市: {city}")


async def calculator(expression: str) -> str:
    await asyncio.sleep(0.05)            # 模拟一次计算服务调用
    return run_calculator(expression)    # W1 写的：出错也返回字符串，不抛异常


TOOLS = {
    "get_weather": (get_weather, "查询某城市今天的气温，参数为城市名，如 get_weather[北京]"),
    "calculator": (calculator, "计算一个算术表达式，如 calculator[20-12]"),
}

async def mock_llm(scratchpad: str) -> str:
    await asyncio.sleep(0.05)            # 模拟一次模型调用
    obs_count = scratchpad.count("Observation:")
    if obs_count == 0:
        return "Thought: 我需要先查北京的气温\nAction: get_weather[北京]"
    if obs_count == 1:
        return "Thought: 拿到北京 12 度，还需要上海的气温\nAction: get_weather[上海]"
    if obs_count == 2:
        return "Thought: 两个温度都有了，计算它们的差\nAction: calculator[20-12]"
    return "Thought: 计算完成，我可以回答了\nFinal Answer: 北京和上海今天的气温相差 8 度。"

async def run_react(question: str, *, brain=mock_llm, tools=TOOLS, max_steps: int = MAX_STEPS) -> RunResult:
    scratchpad = ""                      # 草稿纸：ReAct 的短期记忆
    events = []                          # 今天的新东西：每发生一件事记一条
    for step in range(1, max_steps + 1):
        response = await brain(scratchpad)              # 改动 ①：加了 await
        events.append({"type": "step", "step": step, "text": response})

        if "Final Answer:" in response:
            final = response.split("Final Answer:")[-1].strip()
            events.append({"type": "final", "step": step, "text": final})
            return RunResult(answer=final, events=events)

        action_match = re.search(r"Action:\s*(\w+)\[(.*?)\]", response)
        if action_match:
            tool_name, arg = action_match.group(1), action_match.group(2)
            if tool_name in tools:
                func, _ = tools[tool_name]
                observation = await func(arg)           # 改动 ②：加了 await
            else:
                observation = f"错误：不存在工具 {tool_name}，可用工具：{list(tools.keys())}"
            events.append({"type": "observation", "step": step, "text": observation})
            scratchpad += f"\n{response}\nObservation: {observation}"
        else:
            observation = "格式错误：请严格使用 Action: 工具名[参数] 或 Final Answer: 格式。"
            events.append({"type": "observation", "step": step, "text": observation})
            scratchpad += f"\n{response}\nObservation: {observation}"

    return RunResult(answer="[强制终止] 超过 MAX_STEPS 步 —— 这就是生产中防死循环的保险丝", events=events)