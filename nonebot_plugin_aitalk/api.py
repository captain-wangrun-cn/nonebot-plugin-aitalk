from openai import AsyncOpenAI
from .config import plugin_config
from typing import Tuple

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

    return message, reasoning