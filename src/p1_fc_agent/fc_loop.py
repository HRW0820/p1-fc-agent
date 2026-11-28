"""FC 版 ReAct 循环：没有 Thought / Action / Final Answer，也没有正则。模型递卡就是要用工具，不递卡就是在回答"""
from p1_fc_agent import llm
from p1_fc_agent.calling import ParseError, read_call, run, tool_spec

MAX_STEPS = 8                           # 保险丝：最多问模型几轮


def execute(call: dict, models: list):
    """模型递回来的一张卡：填表、执行，回 (工具名, 结果文字)。卡填错了不抛，把原因当结果"""
    try:
        form = read_call(call, models)
        return form.__class__.__name__, run(form)
    except ParseError as e:             # 填错了：原因当结果递回去，模型下一轮自己改
        return call["function"]["name"], str(e)

async def react_events(question: str, models: list, *, send=llm.post, max_steps: int = MAX_STEPS):
    """每发生一件事就 yield 一条。一轮 = 问模型一次 + 把它递的卡挨个执行、挨个递回去"""
    messages = [{"role": "user", "content": question}]
    tools = [tool_spec(m) for m in models]
    for step in range(1, max_steps + 1):
        content, _, _, calls = await llm.chat(messages, tools=tools, send=send)
        yield {"type": "step", "step": step, "text": content}
        if not calls:                   # 没递卡：这段话就是最终回答
            yield {"type": "final", "step": step, "text": content}
            return
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:              # 一轮递了几张卡，就挨个执行、挨个递回去
            name, observation = execute(call, models)
            yield {"type": "observation", "step": step, "tool": name, "text": observation}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": observation})
    yield {"type": "final", "step": max_steps, "text": f"[强制终止] 超过 {max_steps} 步还没回答 —— 防死循环的保险丝"}

async def run_react(question: str, models: list, **options) -> str:
    """整箱拿：只要最后那句回答"""
    last = ""
    async for event in react_events(question, models, **options):
        last = event["text"]
    return last