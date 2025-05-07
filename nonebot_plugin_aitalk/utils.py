from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    PrivateMessageEvent,
    Bot,
    MessageSegment,
    Message as OneBotMessage,
)
from nonebot.drivers.httpx import httpx
import base64
from io import BytesIO
import json
import random
import aiofiles
import pysilk
from .config import reply_when_meme, reply_msg, tts_config
from .msg_seg import *
from nonebot import logger
from nonebot.utils import run_sync
from fish_audio_sdk import Session, TTSRequest, Prosody
import nonebot_plugin_localstore as store

session = Session(apikey=tts_config.api_key, base_url=tts_config.api_url)


async def send_thinking_msg(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    thinking_msg: str,
    bot_nickname: list,
):
    # 确保 bot_nickname 不为空
    nickname = random.choice(bot_nickname) if bot_nickname else str(event.self_id)

    # 构建转发消息节点
    node_content = [MessageSegment.text(thinking_msg)]  # 思考内容作为文本

    # 尝试构建转发消息
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_forward_msg(
                group_id=event.group_id,
                messages=[
                    MessageSegment.node_custom(
                        user_id=event.self_id,
                        nickname=nickname,
                        content=OneBotMessage(node_content),
                    )
                ],
            )
        elif isinstance(event, PrivateMessageEvent):
            # 私聊可能不支持直接发送自定义节点转发，可以考虑普通消息
            await bot.send_private_msg(
                user_id=event.user_id,
                message=f"({nickname} 正在思考中...)\n{thinking_msg}",
            )
    except Exception as e:
        logger.warning(f"发送思考消息失败: {e}. 尝试普通消息发送。")
        # 失败则发送普通消息
        fallback_msg = f"({nickname} 正在思考中...)\n{thinking_msg}"
        await bot.send(event, fallback_msg)


# 封装重复的代码逻辑，用于发送格式化后的回复
async def send_formatted_reply(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    formatted_reply: list,
    should_reply: bool,
    original_msg_id: str | None = None,  # 添加 original_msg_id 参数
):
    # 确定回复参数
    reply_params = {}
    if should_reply and original_msg_id:
        if isinstance(event, GroupMessageEvent):  # 群聊才真正需要回复消息ID
            reply_params["reply_message"] = True
            # OneBot V11 通常不需要显式传递 message_id 来回复，会自动回复触发事件的消息
            # 但如果需要精确回复特定消息，则需要适配器支持和正确传递
        # 私聊通常不需要 reply_message=True，直接发送即可

    for msg_segment in formatted_reply:  # Renamed 'msg' to 'msg_segment'
        current_reply_params = reply_params.copy()  # 每次发送前复制，避免互相影响

        if isinstance(msg_segment, MessageSegment):
            if msg_segment.type == "image":
                # 图片消息单独处理，结合 reply_when_meme 配置
                if reply_when_meme:  # 只有当配置允许时，图片才带回复
                    await bot.send(event, msg_segment, **current_reply_params)
                else:
                    await bot.send(event, msg_segment)  # 不回复
            else:
                await bot.send(event, msg_segment, **current_reply_params)
        elif isinstance(msg_segment, OneBotMessage):  # 如果是合并后的OneBotMessage
            await bot.send(event, msg_segment, **current_reply_params)
        elif isinstance(msg_segment, PokeMessage):
            try:
                if isinstance(event, GroupMessageEvent):
                    await bot.send_group_msg(
                        group_id=msg_segment.gid,
                        message=MessageSegment.poke(qq=msg_segment.uid),
                    )
                else:  # 私聊戳一戳可能需要特定API或不支持，这里假设发送普通消息提示
                    logger.info(
                        f"尝试在私聊中发送戳一戳给 {msg_segment.uid} (gid: {msg_segment.gid})，通常不支持。"
                    )
                    await bot.send_private_msg(
                        user_id=msg_segment.uid, message="[AI想戳戳你]"
                    )
            except Exception as e:
                logger.error(f"发送戳一戳失败: {e}")
                await bot.send(event, "[AI戳人失败了...]", **current_reply_params)

        elif isinstance(msg_segment, BanUser):
            if isinstance(event, GroupMessageEvent):
                try:
                    member_info = await bot.get_group_member_info(
                        group_id=msg_segment.gid, user_id=bot.self_id, no_cache=True
                    )
                    if member_info["role"] not in ["admin", "owner"]:
                        await bot.send(
                            event,
                            "呀呀呀，我好像没有权限禁言别人呢……",
                            **current_reply_params,
                        )
                        continue  # 使用 continue 跳过当前循环

                    sender_info = await bot.get_group_member_info(
                        group_id=msg_segment.gid, user_id=msg_segment.uid, no_cache=True
                    )
                    if sender_info["role"] in [
                        "admin",
                        "owner",
                    ]:  # 不能禁言管理员或群主
                        await bot.send(
                            event,
                            "呀呀呀，这个人我可不敢禁言……",
                            **current_reply_params,
                        )
                        continue

                    await bot.set_group_ban(
                        group_id=msg_segment.gid,
                        user_id=msg_segment.uid,
                        duration=msg_segment.duration,
                    )
                    await bot.send(
                        event,
                        f"已将用户 {msg_segment.uid} 禁言 {msg_segment.duration} 秒。",
                        **current_reply_params,
                    )

                except Exception as e:
                    logger.error(f"禁言用户失败: {e}")
                    await bot.send(
                        event, "呀呀呀，禁言好像失败了呢……", **current_reply_params
                    )
            else:  # 私聊不能禁言
                pass
        elif isinstance(msg_segment, TTSMessage):
            try:
                tts_file = await fish_audio_tts(
                    text=msg_segment.text,
                    reference_id=msg_segment.reference_id,
                    speed=tts_config.speed,
                    volume=tts_config.volume,
                )
                await bot.send(
                    event,
                    MessageSegment.record(file=tts_file)
                )
            except Exception as e:
                logger.error(f"发送TTS失败: {e}")
                await bot.send(event, "[AI说话失败了...]", **current_reply_params)
        # 如果还有其他自定义类型，在这里添加处理逻辑


def need_reply_msg(reply_json_str: str, event: GroupMessageEvent | PrivateMessageEvent):
    # 判断是否需要回复原消息
    if isinstance(
        event, PrivateMessageEvent
    ):  # 私聊默认不回复原消息 (除非AI明确要求且逻辑支持)
        return False, None

    try:
        # 尝试去除常见的代码块标记
        cleaned_reply = reply_json_str.strip()
        if cleaned_reply.startswith("```json"):
            cleaned_reply = cleaned_reply[7:]
        if cleaned_reply.endswith("```"):
            cleaned_reply = cleaned_reply[:-3]

        msg_data = json.loads(cleaned_reply)  # Renamed 'msg' to 'msg_data'
        # 只有当全局配置允许回复，并且AI的回复字段也要求回复时
        if reply_msg and msg_data.get("reply", False):
            # 对于群聊，使用 event.message_id 作为被回复的消息 ID
            # AI 返回的 msg_id 可能是它理解的用户消息ID，但不一定能直接用于回复
            return True, str(event.message_id)
        return False, None
    except json.JSONDecodeError:  # JSON解析失败，则不回复
        logger.debug(f"need_reply_msg: JSON解析失败, content: {reply_json_str[:100]}")
        return False, None
    except Exception as e:  # 其他异常
        logger.warning(f"need_reply_msg: 发生未知错误: {e}")
        return False, None


async def get_images(event: GroupMessageEvent | PrivateMessageEvent) -> list[str]:
    # 获取图片,返回base64数据
    images = []
    for segment in event.get_message():
        if segment.type == "image":
            image_url = segment.data.get("url")
            if image_url:
                try:
                    images.append(await url2base64(image_url))
                except Exception as e:
                    logger.error(f"下载或转换图片失败: {image_url}, error: {e}")
            else:
                logger.warning("图片消息段缺少 'url' 数据。")
    return images


async def url2base64(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=20.0)  # 增加超时
        response.raise_for_status()  # 确保请求成功
    imgdata = base64.b64encode(response.content).decode("utf-8")
    return imgdata

async def fish_audio_tts(text, reference_id: str = "", speed: float = 1.0, volume: float = 0.0) -> str:
    # FishAudio 语音合成, 返回silk文件路径
    cache_dir = store.get_plugin_cache_dir()
    file_id = random.randint(0,1145141919)
    pcm_file = cache_dir / f"tts_{file_id}.pcm"

    async with aiofiles.open(pcm_file, "wb") as f:
        for chunk in session.tts(TTSRequest(
            reference_id=reference_id,
            text=text,
            format="pcm",
            sample_rate=24000,
            prosody=Prosody(speed=speed, volume=volume),
        )):
            await f.write(chunk)

    silk_file_name = cache_dir / f"tts_{file_id}.silk"
    silk_file = open(silk_file_name, "wb")
    await run_sync(pysilk.encode)(open(pcm_file, "rb"), silk_file, sample_rate=24000, bit_rate=24000)
    silk_file.close()

    return silk_file_name.as_uri()
