import asyncio
from p1_fc_agent.async_tools import fetch_weather

async def fetch_with_timeout(city: str, delay: float = 0.5, timeout: float = 1.0) -> str:
    return await asyncio.wait_for(fetch_weather(city, delay), timeout)

async def retry(make_call, timeout, max_attempts=3, label="tool")-> str:
    """重试工具：如果失败则重试，如果超过最大尝试次数则返回错误。"""
    for attempt in range(1, max_attempts + 1):
        call = make_call()
        try:
            return await asyncio.wait_for(call, timeout)
        except TimeoutError:
            continue
    return f"工具超时: {label}（已尝试 {max_attempts} 次）"

async def gather_resilient(calls, timeout, max_attempts=1):
    """并行调用多个工具，如果其中一个超时则重试，如果超过最大尝试次数则返回错误。"""
    labels = [label for label, _ in calls] 
    # 第一层：每个工具先包上 retry（内部消化 TimeoutError，永不抛它）
    coros = [retry(make_call, timeout, max_attempts, label) for label, make_call in calls]
    # 第二层：gather 收编剩余异常（ValueError 等穿透过来的）
    results = await asyncio.gather(*coros, return_exceptions=True)
    # 第三层：逐项分流——异常降级成喂回文本
    return [f"工具异常: {label}: {type(r).__name__}: {r}" if isinstance(r, Exception) else r
        for label, r in zip(labels, results)]