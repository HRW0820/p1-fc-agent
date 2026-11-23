"""W1 Session 4 · asyncio 演示：串行 vs 并行 + 两个经典坑

跑法：uv run python -m p1_fc_agent.async_demo
看点：① 串行 3s vs 并行 1s 的真实计时
      ② 结尾故意触发的 RuntimeWarning——"忘了 await"的现场（记进 pitfalls）
"""
import asyncio
import time

from p1_fc_agent.async_tools import (
    fetch_all_parallel,
    fetch_all_serial,
    fetch_weather,
)

CITIES = ["北京", "上海", "广州"]


async def demo():
    print("=" * 64)
    print("场景：Agent 同时查 3 个城市的天气，每个请求要 1 秒")
    print("=" * 64)

    print("\n--- 串行版（逐个 await）---")
    t0 = time.monotonic()
    r1 = await fetch_all_serial(CITIES)
    print(f"结果: {r1}")
    print(f"耗时: {time.monotonic() - t0:.2f}s")

    print("\n--- 并行版（asyncio.gather）---")
    t0 = time.monotonic()
    r2 = await fetch_all_parallel(CITIES)
    print(f"结果: {r2}")
    print(f"耗时: {time.monotonic() - t0:.2f}s")

    print("\n" + "=" * 64)
    print(f"结论：结果完全一致，耗时 {3:.0f}s → 1s。")
    print("Agent 的延迟优化，一半靠并发工具调用。")
    print("=" * 64)

    # ---- 经典坑现场：调用 async 函数但忘了 await ----
    print("\n【坑演示】下面这行调用 fetch_weather 却没 await：")
    lazy = fetch_weather("杭州", delay=0.1)
    print(f"  lazy = {lazy!r:.60}")
    print("  type:", type(lazy).__name__, "← 没执行！是个'懒'对象")
    print("  程序结束时会看到 RuntimeWarning: coroutine was never awaited")
    print("  （故意不 await 它——请把这个坑记进 pitfalls.md，编号 P004）")
    # lazy 从未被 await，解释器回收时会发出 RuntimeWarning


asyncio.run(demo())
