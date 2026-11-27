"""裸调真模型的最小封装：读 key、发一段对话、算钱。真发网络请求的只有 post 一个函数"""
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
PRICE = {"hit": 0.02, "miss": 1.0, "out": 4.0}     # 空闲时段单价，元 / 百万 token；高峰时段（工作日 9-12 点、14-18 点）翻倍


def load_api_key(env_file: str = ".env") -> str:
    """读 DEEPSEEK_API_KEY。env_file 默认是当前目录的 .env：所以命令都要在仓库根目录运行"""
    load_dotenv(env_file)                          # 把文件里的 DEEPSEEK_API_KEY=... 装进环境变量；环境变量里已有的不覆盖
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError(f"没有找到 DEEPSEEK_API_KEY：请在仓库根目录的 {env_file} 里写一行 DEEPSEEK_API_KEY=你的key")
    return key

async def post(payload: dict) -> dict:
    """唯一真的发网络请求的函数。测试从来不碰它，只有验收脚本走这里"""
    thinking = payload.pop("thinking")             # SDK 不认 thinking 这个参数，只认 extra_body 里的
    client = AsyncOpenAI(base_url=BASE_URL, api_key=load_api_key())
    resp = await client.chat.completions.create(**payload, extra_body={"thinking": thinking})
    return resp.model_dump()                       # 整份响应变成字典：choices、usage 都在里面


async def chat(messages: list[dict], *, send=post, max_tokens: int = 256, temperature: float = 0.0):
    """发一段对话，返回 (回复文本, 用量)。send 可以换成假的：测试不花钱"""
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
               "temperature": temperature, "thinking": {"type": "disabled"}}     # 关思考：只要回答，不要思考过程
    data = await send(payload)
    return data["choices"][0]["message"]["content"], data["usage"]

def cost(usage: dict, price: dict = PRICE) -> float:
    """这次调用花了多少元。usage 就是响应里的用量"""
    hit = usage["prompt_cache_hit_tokens"]        # 缓存命中的输入：同样的开头，第二次起便宜很多
    miss = usage["prompt_tokens"] - hit           # 其余的输入
    return (hit * price["hit"] + miss * price["miss"] + usage["completion_tokens"] * price["out"]) / 1_000_000
