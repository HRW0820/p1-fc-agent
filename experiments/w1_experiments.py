"""W1 验收 · 并发实验报告的实验脚本（可复现）

跑法：uv run python experiments/w1_experiments.py
产出：5 组实验的真实计时数据 + 错误喂回文本示例——报告里所有数字都来自本脚本输出。
素材全部来自本项目模块：async_tools（串行/并行）、resilient_tools（超时/重试/收编）。
"""
import asyncio
import time

from p1_fc_agent.async_tools import fetch_all_parallel, fetch_all_serial
from p1_fc_agent.resilient_tools import fetch_with_timeout, gather_resilient, retry


def timed(label: str, coro):
    """计时跑一个协程，返回 (耗时, 结果)。"""
    t0 = time.monotonic()
    result = asyncio.run(coro)
    elapsed = time.monotonic() - t0
    print(f"  {label:<38} {elapsed:6.2f}s")
    return elapsed, result


def cpu_task(n: int = 2_500_000) -> int:
    """CPU 密集任务：纯计算循环（无 await = 无让出点）。"""
    total = 0
    for i in range(n):
        total += i * i
    return total


CITIES = ["北京", "上海", "广州", "杭州", "成都", "深圳", "南京", "武汉", "西安", "重庆"]


def exp1_serial_vs_parallel():
    print("\n" + "=" * 62)
    print("实验一：串行 vs 并行的规模效应（每个工具 0.5s）")
    print("=" * 62)
    print(f"  {'场景':<38} {'耗时':>7}")
    for n in (3, 5, 10):
        cities = CITIES[:n]
        serial, _ = timed(f"串行 N={n}（预期≈{n*0.5:.1f}s）",
                          fetch_all_serial(cities, [0.5] * n))
        parallel, _ = timed(f"并行 gather N={n}（预期≈0.5s）",
                            fetch_all_parallel(cities, [0.5] * n))
        print(f"  → 加速比 {serial/parallel:.1f}x")


def exp2_timeout_cancels():
    print("\n" + "=" * 62)
    print("实验二：wait_for 超时会取消任务（delay=1.0, timeout=0.3）")
    print("=" * 62)
    elapsed = None
    t0 = time.monotonic()
    try:
        asyncio.run(fetch_with_timeout("慢城", delay=1.0, timeout=0.3))
    except TimeoutError:
        elapsed = time.monotonic() - t0
    print(f"  {'超时抛出耗时（<0.6 证明已取消）':<38} {elapsed:6.2f}s")
    print("  → 若未取消（等任务跑完再抛）应为 1.0s+；实测远小于它")


def exp3_retry_recovers():
    print("\n" + "=" * 62)
    print("实验三：瞬态故障自愈（第1次超时，第2次成功）")
    print("=" * 62)
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            await asyncio.sleep(1.0)      # 抖一下
        return f"天气API: 晴 25 度"

    timed("retry(flaky, timeout=0.3, max=3)", retry(flaky, timeout=0.3, max_attempts=3, label="天气API"))
    print(f"  → 实际调用 {calls['n']} 次：第1次超时被消化，第2次成功交付")


def exp4_fault_isolation():
    print("\n" + "=" * 62)
    print("实验四：批量故障隔离（1 个永久挂 + 2 个正常）")
    print("=" * 62)

    def make(city, dead=False):
        async def tool():
            await asyncio.sleep(1.0 if dead else 0.1)
            return f"{city}: 晴 25 度"
        return tool

    calls = [("北京API", make("北京")), ("上海API", make("上海", dead=True)), ("广州API", make("广州"))]
    elapsed, results = timed("gather_resilient(timeout=0.3, max=2)",
                             gather_resilient(calls, timeout=0.3, max_attempts=2))
    print(f"  → 最慢成员路径 = 死工具重试 2 次 × 0.3s ≈ {elapsed:.2f}s")
    print("  → 最终结果（错误已降级成喂回文本）：")
    for r in results:
        print(f"     {r!r}")


def exp5_cpu_bound():
    print("\n" + "=" * 62)
    print("实验五：CPU 密集任务 asyncio 无加速（对照组）")
    print("=" * 62)

    async def wrap_cpu():
        return cpu_task()

    async def parallel_cpu():
        # gather 必须在协程体内调用：顶层直接 asyncio.gather(...) 会因
        # "没有当前事件循环" 而 RuntimeError（本脚本第一版踩过，记 P007）
        return await asyncio.gather(wrap_cpu(), wrap_cpu())

    t0 = time.monotonic()
    cpu_task(); cpu_task()
    serial = time.monotonic() - t0
    print(f"  {'串行 2 次纯计算':<38} {serial:6.2f}s")

    t0 = time.monotonic()
    asyncio.run(parallel_cpu())
    parallel = time.monotonic() - t0
    print(f"  {'gather 2 次纯计算':<38} {parallel:6.2f}s")
    print(f"  → 加速比 {serial/parallel:.2f}x（≈1.0 = 无加速；asyncio 优化等待不优化计算）")


if __name__ == "__main__":
    print("W1 并发实验 · 全部数据来自本项目模块的真实运行")
    exp1_serial_vs_parallel()
    exp2_timeout_cancels()
    exp3_retry_recovers()
    exp4_fault_isolation()
    exp5_cpu_bound()
    print("\n结论见《W1-并发实验报告.md》")
