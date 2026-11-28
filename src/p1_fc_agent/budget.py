"""单次会话的账本：记 token、算钱，超过上限就喊停。一次会话 = 一个 ReAct 循环从头跑到尾"""
from p1_fc_agent import llm

DEFAULT_LIMIT = 0.01                      # 一次会话最多花多少元；打完电话才知道花了多少，所以最多会超一次电话的钱


class OverBudget(Exception):
    """这次会话花的钱超过了上限"""


class Budget:
    def __init__(self, limit_yuan: float = DEFAULT_LIMIT, price: dict = llm.PRICE):
        """limit_yuan 是上限；price 默认是空闲时段单价，高峰时段要传翻倍的那份（见 W3 Day 7 笔记）"""
        self.limit_yuan = limit_yuan
        self.price = price
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.spent = 0.0

    def charge(self, usage: dict) -> None:
        """每打完一次电话记一笔。先记全，再看超没超：超了就抛 OverBudget"""
        self.calls += 1
        self.prompt_tokens += usage["prompt_tokens"]
        self.completion_tokens += usage["completion_tokens"]
        self.spent += llm.cost(usage, self.price)
        if self.spent > self.limit_yuan:
            raise OverBudget(f"已花 {self.spent:.6f} 元，超过上限 {self.limit_yuan} 元")

    def report(self) -> dict:
        """账单：给客人看、写进日志都用这一份"""
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens, "spent": round(self.spent, 6)}
