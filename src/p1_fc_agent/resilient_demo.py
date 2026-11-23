"""W1 Session 5 · 韧性层演示：工具超时 → 重试 → 成功 / 失败隔离

跑法：uv run python -m p1_fc_agent.resilient_demo
看点：① 单个"抖动后恢复"工具的完整重试轨迹
      ② 批量调用中一个工具永久挂掉——其余照常交付，失败被降级成喂回文本
"""
import asyncio
import time

from p1_fc_agent.resilient_tools import gather_resilient, retry


def make_flaky_tool(fail_times: int, label: str):
    """前 fail_times 次慢到超时，之后瞬间成功（模拟网络抖动后恢复）。"""
    calls = {"n": 0}

    async def tool():
        calls["n"] += 1
        print(f"    [{label}] 第 {calls['n']} 次调用，{'慢(将超时)' if calls['n'] <= fail_times else '快'}")
        if calls["n"] <= fail_times:
            await asyncio.sleep(1.0)
        return f"{label}: 晴 25 度"

    return tool, calls


async def demo():
    print("=" * 64)
    print("场景一：Agent 调一个天气 API，它抖了一下（第1次超时）")
    print("=" * 64)

    tool, calls = make_flaky_tool(fail_times=1, label="天气API")
    t0 = time.monotonic()
    result = await retry(tool, timeout=0.4, max_attempts=3, label="天气API")
    print(f"  轨迹：第1次超时 → 重试 → 第2次成功")
    print(f"  结果: {result!r}（共调用 {calls['n']} 次）")
    print(f"  耗时: {time.monotonic() - t0:.2f}s（一次超时 0.4s + 一次秒成）")

    print()
    print("=" * 64)
    print("场景二：并行调 3 个工具，其中一个永久挂了")
    print("=" * 64)

    ok1, _ = make_flaky_tool(fail_times=0, label="北京API")
    dead, _ = make_flaky_tool(fail_times=99, label="上海API")
    ok2, _ = make_flaky_tool(fail_times=0, label="广州API")

    print("  并行发起：北京 / 上海(永久超时) / 广州，每个 timeout=0.3，重试 2 次")
    t0 = time.monotonic()
    results = await gather_resilient(
        [("北京API", ok1), ("上海API", dead), ("广州API", ok2)],
        timeout=0.3,
        max_attempts=2,
    )
    elapsed = time.monotonic() - t0

    print(f"\n  最终 results（位置即身份）:")
    for i, r in enumerate(results):
        print(f"    results[{i}] = {r!r}")

    print()
    print("=" * 64)
    print(f"结论：一个工具永久挂掉，整批耗时 {elapsed:.2f}s，其余两个照常交付；")
    print("失败被降级成文本——下一步就是把它拼进 Observation 喂回模型，")
    print("模型自己决定：换个工具、换个参数，还是告诉用户'上海查不到'。")
    print("=" * 64)


asyncio.run(demo())
