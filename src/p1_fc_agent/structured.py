"""结构化输出：让模型按一张固定的表格回答。回答变不成表格时，报一句能照着做的话"""
import json
from pydantic import ValidationError
from p1_fc_agent import llm
from p1_fc_agent.tools import format_validation_error

JSON_MODE = {"type": "json_object"}       # JSON 模式：模型保证回合法 JSON，不保证字段对


class ParseError(Exception):
    """模型的回答变不成一张填好的表格。报错信息是一句能照着做的话"""


def parse(text: str, model):
    """把模型回的一段文字变成 model 的一张表。两种死法都接住"""
    try:
        data = json.loads(text)                       # 第一关：这段文字是不是 JSON
    except json.JSONDecodeError as e:                 # 死法一：围栏、只有空格、说到一半被掐断
        raise ParseError(f"不是合法的 JSON：{e.msg}（第 {e.lineno} 行第 {e.colno} 列）") from e
    try:
        return model.model_validate(data)             # 第二关：是 JSON，但表格填对了吗（W1 的安检机）
    except ValidationError as e:                      # 死法二：城市是空的、自己加了字段、根本不是对象
        raise ParseError(f"是合法的 JSON，但表格没填对：{format_validation_error(e)}") from e

async def ask_json(messages: list[dict], model, *, send=llm.post, max_tokens: int = 256):
    """让模型按 model 这张表格回答，返回 (填好的表格, 用量)。send 可以换成假的"""
    fields = "、".join(model.model_fields)                # 字段名从表格上读，不手写：表格改了，店规跟着改
    rule = {"role": "system", "content": f"只输出一个 JSON 对象，不要解释。字段：{fields}"}
    text, usage, finish_reason, _ = await llm.chat([rule] + messages, send=send, max_tokens=max_tokens,
                                                response_format=JSON_MODE)
    if finish_reason != "stop":                         # P015 的欠账：话没说完，JSON 一定是断的，别拿去解析
        raise ParseError(f"模型的回答没说完（finish_reason={finish_reason}），JSON 是断的")
    return parse(text, model), usage
