"""W3-S5 对照实验脚本（可复现）：文本协议（W2 的 react_loop）对 Function Calling（fc_loop）

跑法：uv run python experiments/w3_compare.py [每格跑几遍，默认 10] [结果写到哪个 json] [哪道题：base 或 hard，默认 base] [loose：文本协议改用写松的提示词]
     例：uv run python experiments/w3_compare.py 10 experiments/w3_compare_results.json base
做法：同一个问题，两个循环各跑 N 遍；temperature=0.0 一轮、0.7 一轮。四格交替跑（先文本后 FC），一共 4×N 次。
     每次记下：有没有答完、答案对不对、解析失败几次、走了几轮、打了几次电话、用了多少 token、花了多少元。
重新打分：uv run python experiments/w3_compare.py rescore <结果 json>   改了统计口径后用：按保存的原始记录重算，不重跑、不花钱
花钱：真调模型。四格各 10 遍约 0.1 元（空闲时段）。
产出：逐次结果（json）+ 汇总表（屏幕）——报告里的数字都来自这里。
报告里的三组：base（两城市）、hard（三城市）、loose（两城市 + 写松的提示词），结果各在一个 json 里。
"""
import asyncio
import json
import re
import sys
import time
from collections import Counter

from p1_fc_agent import fc_loop, llm, react_loop
from p1_fc_agent.calling import ParseError, read_call
from p1_fc_agent.tools import CalcQuery, WeatherQuery

QUESTIONS = {"base": ("北京和上海今天的气温相差多少度？", "8"),                 # 两城市：答案 8
             "hard": ("北京、上海、广州这三个城市今天气温最高和最低相差多少度？", "13")}   # 三城市：答案 13（25-12）
QUESTION = QUESTIONS["base"][0]
EXPECTED = "8"
FC_TOOLS = [WeatherQuery, CalcQuery]          # 和文本协议那边的两个工具一一对应，才是公平对照
TEXT_TOOLS = ["get_weather", "calculator"]
TEMPERATURES = (0.0, 0.7)
ACTION = re.compile(r"Action:\s*(\w+)\[(.*?)\]")   # 和 react_loop 里那条正则一样，这里只用来抄轨迹

PROMPT = """你在回答一个问题，可以反复使用下面的工具。

每一轮只输出下面三种格式中的一种，不要输出其他内容：
Thought: 你的想法
Action: get_weather[城市名]
或
Action: calculator[算式]
或
Final Answer: 最终答案

可用工具：
- get_weather[城市名]：查询某城市今天的气温，例如 get_weather[北京]
- calculator[算式]：计算一个算术表达式，例如 calculator[20-12]

问题：{question}{history}"""

PROMPT_LOOSE = """你在回答一个问题，可以反复使用下面两个工具：get_weather（查某个城市今天的气温）、calculator（算一个算式）。
请像 ReAct 那样一步步来：先写你的思考，要用工具就用工具，最后给出最终答案。

问题：{question}{history}"""   # 写松的版本：不给格式样例，只说"像 ReAct 那样"


class Meter:
    """替 llm.post 数数：打了几次电话、每次为什么停、用了多少 token、花了多少元"""

    def __init__(self):
        self.calls = []

    async def send(self, payload):
        t0 = time.monotonic()
        reply = await llm.post(payload)
        self.calls.append({"usage": reply["usage"], "finish": reply["choices"][0]["finish_reason"],
                           "seconds": time.monotonic() - t0})
        return reply

    def tokens(self):
        return sum(c["usage"]["prompt_tokens"] for c in self.calls), sum(c["usage"]["completion_tokens"] for c in self.calls)

    def cost(self):
        return sum(llm.cost(c["usage"]) for c in self.calls)


def text_brain(temperature: float, meter: Meter):
    """文本协议的真模型大脑：接在 react_loop 的 brain= 这个口上。提示词里写好三种格式"""
    async def brain(scratchpad: str) -> str:
        history = f"\n\n这是到目前为止的记录，接着往下写一轮：\n{scratchpad.strip()}" if scratchpad else ""
        messages = [{"role": "user", "content": PROMPT.format(question=QUESTION, history=history)}]
        text, _, _, _ = await llm.chat(messages, temperature=temperature, send=meter.send)
        return text or ""
    return brain


def text_trace(raw_steps: list) -> tuple[str, int]:
    """文本协议实际执行了什么（循环每轮只认第一个 Action），以及模型有几轮自己写了 Observation / 观察（工具结果是它编的）"""
    executed = [m.groups() for m in (ACTION.search(s) for s in raw_steps) if m]
    fabricated = sum("Observation" in s or "观察" in s for s in raw_steps)
    return " → ".join(f"{n}[{a}]" for n, a in executed), fabricated


def is_correct(answer: str) -> bool:
    return bool(re.search(rf"(?<!\d){EXPECTED}(?!\d)", answer))      # 答案里有一个单独的期望数字


async def run_text(temperature: float) -> dict:
    meter = Meter()
    result = await react_loop.run_react(QUESTION, brain=text_brain(temperature, meter))
    events = result.events
    observations = [e["text"] for e in events if e["type"] == "observation"]
    steps = [e for e in events if e["type"] == "step"]
    final = [e for e in events if e["type"] == "final"]
    forced = not final and bool(events)
    trace, fabricated = text_trace([e["text"] for e in steps])
    return {
        "forced": forced, "answer": final[-1]["text"] if final else "",
        "parse_failures": sum(t.startswith("格式错误") for t in observations),
        "parse_messages": [t for t in observations if t.startswith("格式错误")],
        "unknown_tool": sum(t.startswith("错误：不存在工具") for t in observations),
        "used_calculator": "calculator[" in trace,          # 按实际执行算：模型写了但没被执行的不算
        "actions": trace, "fabricated_observations": fabricated,
        "raw_steps": [e["text"] for e in steps],
        "steps": len(steps), "calls": len(meter.calls), "finishes": dict(Counter(c["finish"] for c in meter.calls)),
        "prompt_tokens": meter.tokens()[0], "completion_tokens": meter.tokens()[1],
        "cost": meter.cost(), "seconds": round(sum(c["seconds"] for c in meter.calls), 2),
    }


async def run_fc(temperature: float) -> dict:
    meter = Meter()
    fails = []
    real_execute = fc_loop.execute

    def spy(call, models):                                # 卡填错了不抛，所以在这里拦一道，只为数数
        try:
            read_call(call, models)
        except ParseError as e:
            fails.append(str(e))
        return real_execute(call, models)

    fc_loop.execute = spy
    try:
        events = [e async for e in fc_loop.react_events(QUESTION, FC_TOOLS, send=meter.send, temperature=temperature)]
    finally:
        fc_loop.execute = real_execute
    observations = [e for e in events if e["type"] == "observation"]
    final = [e for e in events if e["type"] == "final"]
    forced = bool(final) and final[-1]["text"].startswith("[强制终止]")
    return {
        "forced": forced, "answer": final[-1]["text"] if final else "",
        "parse_failures": len(fails), "parse_messages": fails,
        "unknown_tool": sum("不存在" in t for t in fails), "fabricated_observations": 0,
        "used_calculator": any(e["tool"] == "CalcQuery" for e in observations),
        "actions": " → ".join(e["tool"] for e in observations),
        "raw_steps": [e["text"] for e in events if e["type"] == "step"],
        "steps": max(e["step"] for e in events), "calls": len(meter.calls),
        "finishes": dict(Counter(c["finish"] for c in meter.calls)),
        "prompt_tokens": meter.tokens()[0], "completion_tokens": meter.tokens()[1],
        "cost": meter.cost(), "seconds": round(sum(c["seconds"] for c in meter.calls), 2),
    }


async def one(loop: str, temperature: float, run_no: int) -> dict:
    t0 = time.monotonic()
    record = {"loop": loop, "temperature": temperature, "run": run_no, "time": time.strftime("%H:%M:%S"), "error": None}
    try:
        record.update(await (run_text if loop == "text" else run_fc)(temperature))
    except Exception as e:                                # 整次跑挂了（比如 API 报 400）：记下来，不算成功
        record["error"] = f"{type(e).__name__}: {e}"[:300]
    record["correct"] = record["error"] is None and not record.get("forced") and is_correct(record.get("answer", ""))
    record["wall_seconds"] = round(time.monotonic() - t0, 2)
    print(f"  {loop:<4} T={temperature} #{run_no:<2} {'OK ' if record['correct'] else 'BAD'} "
          f"steps={record.get('steps', '-')} calls={record.get('calls', '-')} parse_fail={record.get('parse_failures', '-')} "
          f"{record.get('actions', record['error'] or '')[:90]}", flush=True)
    return record


def summarize(records: list) -> list:
    rows = []
    for loop, temperature in [(l, t) for l in ("text", "fc") for t in TEMPERATURES]:
        rs = [r for r in records if r["loop"] == loop and r["temperature"] == temperature]
        n = len(rs)
        ok = [r for r in rs if r["correct"]]
        clean = [r for r in rs if r["error"] is None]
        avg = lambda key: sum(r.get(key, 0) for r in clean) / len(clean) if clean else 0
        rows.append({
            "loop": loop, "temperature": temperature, "n": n, "correct": len(ok),
            "forced": sum(bool(r.get("forced")) for r in clean), "errors": sum(r["error"] is not None for r in rs),
            "parse_failures": sum(r.get("parse_failures", 0) for r in clean),
            "runs_with_parse_failure": sum(r.get("parse_failures", 0) > 0 for r in clean),
            "unknown_tool": sum(r.get("unknown_tool", 0) for r in clean),
            "fabricated_runs": sum(r.get("fabricated_observations", 0) > 0 for r in clean),
            "fabricated_total": sum(r.get("fabricated_observations", 0) for r in clean),
            "used_calculator": sum(bool(r.get("used_calculator")) for r in clean),
            "avg_steps": round(avg("steps"), 1), "avg_calls": round(avg("calls"), 1),
            "avg_prompt_tokens": round(avg("prompt_tokens")), "avg_completion_tokens": round(avg("completion_tokens")),
            "truncated": sum(r.get("finishes", {}).get("length", 0) for r in clean),
            "avg_cost": round(avg("cost"), 5), "total_cost": round(sum(r.get("cost", 0) for r in rs), 5),
            "avg_seconds": round(avg("seconds"), 1),
            "distinct_trajectories": len({r.get("actions") for r in clean}),
            "distinct_answers": len({r.get("answer") for r in clean}),
        })
    return rows


def print_summary(rows: list) -> None:
    print("\n" + "=" * 124)
    print(f"{'':<14}{'对':>5}{'强制终止':>9}{'整次报错':>9}{'解析失败次':>11}{'有失败的遍':>11}{'不存在的工具':>13}{'自编观察 遍/次':>15}{'用计算器':>9}"
          f"{'均轮':>6}{'均电话':>7}{'截断':>6}{'均输出tok':>11}{'均耗时s':>9}{'花费元':>9}{'轨迹种数':>9}{'答案种数':>9}")
    for r in rows:
        print(f"{r['loop'] + ' T=' + str(r['temperature']):<14}{r['correct']:>3}/{r['n']:<2}{r['forced']:>7}{r['errors']:>8}"
              f"{r['parse_failures']:>9}{r['runs_with_parse_failure']:>9}{r['unknown_tool']:>10}{r['fabricated_runs']:>9}/{r['fabricated_total']:<4}{r['used_calculator']:>4}"
              f"{r['avg_steps']:>8}{r['avg_calls']:>7}{r['truncated']:>7}{r['avg_completion_tokens']:>9}"
              f"{r['avg_seconds']:>10}{r['total_cost']:>11.4f}{r['distinct_trajectories']:>8}{r['distinct_answers']:>8}")
    print("=" * 124)


def rescore(path: str) -> None:
    """按 json 里保存的原始记录重新统计轨迹、自编观察、用没用计算器，再重算汇总表"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for r in data["runs"]:
        if r["loop"] == "text" and r["error"] is None:
            r["actions"], r["fabricated_observations"] = text_trace(r["raw_steps"])
            r["used_calculator"] = "calculator[" in r["actions"]
    data["summary"] = summarize(data["runs"])
    data["rescored_at"] = time.strftime("%Y-%m-%d %H:%M:%S") + "，按保存的原始记录重新统计，没有重跑"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print_summary(data["summary"])


async def main(n: int, out: str | None) -> None:
    print(f"问题：{QUESTION}\n每格 {n} 遍，开始 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    records = []
    for temperature in TEMPERATURES:
        print(f"--- temperature={temperature}")
        for run_no in range(1, n + 1):
            records.append(await one("text", temperature, run_no))
            records.append(await one("fc", temperature, run_no))
    rows = summarize(records)
    print_summary(rows)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"question": QUESTION, "expected": EXPECTED, "n": n, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "summary": rows, "runs": records}, f, ensure_ascii=False, indent=1)
        print(f"逐次结果写到 {out}")


if __name__ == "__main__":
    QUESTION, EXPECTED = QUESTIONS[sys.argv[3] if len(sys.argv) > 3 else "base"]
    if len(sys.argv) > 1 and sys.argv[1] == "rescore":
        rescore(sys.argv[2])
        sys.exit(0)
    if len(sys.argv) > 4 and sys.argv[4] == "loose":              # 只换文本协议的提示词；FC 没有提示词可换
        PROMPT = PROMPT_LOOSE
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10, sys.argv[2] if len(sys.argv) > 2 else None))
