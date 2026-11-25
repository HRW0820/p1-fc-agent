import json
import asyncio

def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

async def token_stream(text: str, delay: float = 0.05):
    for index, char in enumerate(text):
        if delay:
            await asyncio.sleep(delay)
        yield sse({"type": "token", "index": index, "content": char})
    yield sse({"type": "done", "count": len(text)})