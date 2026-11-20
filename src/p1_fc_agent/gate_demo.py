"""W1 Session 3 · 海关演示：坏参数 → 拦截 → 错误喂回 → 模型自纠错

这是微缩版 ReAct 循环（剧本式"模型"）：模型连续传坏参数，
run_calculator 的海关把它们拦下并转成 Observation 喂回，
第三次模型修正成功。

跑法：uv run python -m p1_fc_agent.gate_demo
"""
from p1_fc_agent.tools import run_calculator

# 剧本：模拟模型的三次调用尝试（前两次坏，第三次好）
MODEL_ATTEMPTS = [
    "",              # 坏1：空表达式（幻觉常见形态：该给参数时给了空）
    "import os",     # 坏2：越界内容（试图走私代码进 eval）
    "20 - 12",       # 好：正经的算式
]

scratchpad = []  # Agent 的记忆：不断追加

print("=" * 64)
print("微缩 ReAct：错误是喂回去的，不是抛出去的")
print("=" * 64)

for step, expression in enumerate(MODEL_ATTEMPTS, 1):
    print(f"\n────── 第 {step} 步 ──────")
    print(f"Thought: 模型决定调用 calculator，参数 expression={expression!r}")
    print(f"Action:  calculator[{expression!r}]")

    observation = run_calculator(expression)   # ← 海关在这里工作
    print(f"Observation: {observation}")

    scratchpad.append(f"Action: calculator[{expression!r}]\nObservation: {observation}")
    if not observation.startswith("参数校验失败"):
        print("\nThought: 计算成功，任务完成。")
        print(f"Final Answer: {observation}")
        break
    # 否则：错误已在 scratchpad 里，下一轮模型会看到它并修正
    print("  （错误已拼进记忆，下一轮模型能看到并修正）")

print("\n" + "=" * 64)
print("轨迹复盘：模型第 1、2 步传坏参数 → 循环没崩 → 错误变成")
print("Observation 喂回 → 第 3 步自纠错成功。循环一行都没改，")
print("可靠性全部来自工具层的海关。这就是 W3 FC Agent 的工具形态。")
