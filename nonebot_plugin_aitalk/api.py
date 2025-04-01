from openai import AsyncOpenAI
from .config import plugin_config
from typing import Tuple
import re

def extract_thinking_content(text):
    # 提取思维链内容和正文内容
    pattern = r"<think>(.*?)</think>"  # 匹配 <think> 标签及其内容
    match = re.search(pattern, text, re.DOTALL)  # 使用 re.search 匹配任意位置

    if match:
        think_content = match.group(1).strip()  # 提取思维链内容
        # 提取正文内容：去掉 <think> 标签及其内容
        content = re.sub(pattern, "", text).strip()
        return think_content, content
    else:
        # 如果没有匹配到 <think> 标签，返回 None
        return None, text.strip()

async def gen(
        messages: dict, 
        model_name: str, 
        api_key: str, 
        api_url: str
) -> Tuple[str | None, str | None]:
    client = AsyncOpenAI(base_url=api_url, api_key=api_key)

    completion = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=plugin_config.aitalk_completion_config.max_token,
        temperature=plugin_config.aitalk_completion_config.temperature,
        top_p=plugin_config.aitalk_completion_config.top_p,
    )
    
    message = completion.choices[0].message.content
    reasoning = ""
    
    if "reasoning_content" in completion.choices[0].message.model_extra:
        reasoning = completion.choices[0].message.model_extra["reasoning_content"]
    elif "<think>" in message and "</think>" in message:
        reasoning, message = extract_thinking_content(message)

    return message, reasoning