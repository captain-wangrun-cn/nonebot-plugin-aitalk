from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot, MessageSegment, Message
from nonebot.drivers.httpx import httpx
import base64
from io import BytesIO
import json
import re
import random
from .config import reply_when_meme, reply_msg

class PokeMessage:
    gid = 0
    uid = 0

async def send_thinking_msg(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    thinking_msg: str,
    bot_nickname: list,
):
    nickname = random.choice(bot_nickname)
    msg = [MessageSegment(
        type="node",
        data={
            "name": nickname,
            "uin": str(event.self_id),
            "content": thinking_msg,
        }
    )]
    send_kwargs = {}
    if isinstance(event, PrivateMessageEvent):
        send_kwargs["user_id"] = event.user_id
    else:
        send_kwargs["group_id"] = event.group_id
    await bot.send_msg(message=msg, **send_kwargs)

# 封装重复的代码逻辑，用于发送格式化后的回复
async def send_formatted_reply(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    formatted_reply: list,
    should_reply: bool  # 明确使用布尔值
):
    for msg in formatted_reply:
        if isinstance(msg, MessageSegment):
            if msg.type == "image":
                # 图片消息单独处理，结合 reply_when_meme 配置
                await bot.send(event, msg, reply_message=reply_when_meme and should_reply)
            else:
                await bot.send(event, msg, reply_message=should_reply)
        elif isinstance(msg, list):
            # 将多段内容合并到一条消息
            result_msg = Message()
            for msg_ in msg:
                result_msg += msg_
            await bot.send(event, result_msg, reply_message=should_reply)
        elif isinstance(msg, PokeMessage):
            # 戳一戳
            if isinstance(event,GroupMessageEvent):
                await bot.group_poke(group_id=msg.gid, user_id=msg.uid)
            else:
                await bot.friend_poke(user_id=msg.uid)

def need_reply_msg(reply: str):
    # 判断是否需要回复原消息
    try:
        msg = json.loads(reply.replace("```json", "").replace("```", ""))
        # 只有当配置允许回复时，才检查 AI 的回复字段
        if reply_msg and msg.get("reply", False):
            return True, msg.get("msg_id")
        return False, None
    except Exception:
        return False, None

async def get_images(event: GroupMessageEvent|PrivateMessageEvent) -> list[str]:
    # 获取图片,返回base64数据
    images = []
    for segment in event.get_message():
        if segment.type == "image":
            images.append(await url2base64(segment.data["url"]))
    return images

async def url2base64(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    # 将base64编码进行解码
    imgdata=base64.b64encode(response.content).decode("utf-8")
    return imgdata
  
def extract_thinking_content(text):
    # 提取思维链内容和正文内容
    pattern = r"<think>(.*?)</think>"  # 匹配 <think> 标签及其内容
    match = re.search(pattern, text, re.DOTALL)  # 使用 re.search 匹配任意位置

    if match:
        think_content = match.group(1).strip()  # 提取思维链内容
        # 提取正文内容：去掉 <think> 标签及其内容
        content = re.sub(pattern, "", text).strip()
        print(content)
        return think_content, content
    else:
        # 如果没有匹配到 <think> 标签，返回 None
        return None, text.strip()
