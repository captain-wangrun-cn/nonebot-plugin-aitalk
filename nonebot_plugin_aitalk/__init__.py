import os
from pathlib import Path  # 引入 Path
from nonebot import on_message, on_command, get_driver, require, logger
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.permission import SUPERUSER
from nonebot.adapters import Message  # Message 类型用于 CommandArg
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    PrivateMessageEvent,
    GROUP,
    GROUP_ADMIN,
    GROUP_OWNER,
    PRIVATE_FRIEND,
    MessageSegment,
    Message as OneBotMessage,  # 明确这是 OneBot V11 的 Message
    Bot,
)

require("nonebot_plugin_localstore")

import json, time, random
from .config import *
from .api import gen
from .data import *
from .cd import *
from .utils import *
from .msg_seg import *


__plugin_meta__ = PluginMetadata(
    name="简易AI聊天",
    description="简单好用的AI聊天插件。支持多API、图片理解、语音合成、表情包、提醒、戳一戳等。群聊提示词通过在指定目录创建 {GROUP_ID}.txt 文件进行配置。",
    usage=(
        "@机器人发起聊天\n"
        "/选择模型 <模型名>\n"
        "/清空聊天记录\n"
        "/ai对话 <开启/关闭>\n\n"
        "群聊专属提示词配置方法：\n"
        f"1. 在您的机器人配置文件 (例如 .env.prod) 或 nonebot 项目的 `config.py` 中，确保 `aitalk_group_prompts_dir` 配置项指向了您希望存放群提示词文件的目录 (默认是: '{plugin_config.aitalk_group_prompts_dir}')。\n"
        "   请使用相对于机器人运行根目录的路径。\n"
        "2. 在上述目录下，为需要自定义提示词的群聊创建一个文本文件，文件名格式为 `群号.txt` (例如: `1234567.txt`)。\n"
        "3. 将该群聊专属的AI性格设定/提示词内容写入此文本文件中并保存 (使用 UTF-8 编码)。\n"
        "4. 修改提示词文件后，建议在该群聊中使用 `/清空聊天记录` 命令，或重启机器人，以确保新的提示词在对话中完全生效。"
    ),
    type="application",
    homepage="https://github.com/captain-wangrun-cn/nonebot-plugin-aitalk",
    config=Config,  # 引用配置类
    supported_adapters={"~onebot.v11"},
)

driver = get_driver()
user_config = {
    "private": {},
    "group": {},
}  # 用户配置，主要用于存储模型选择、聊天记录等运行时状态
memes = [dict(i) for i in available_memes]
model_list = [i.name for i in api_list]
sequence = {"private": [], "group": []}  # 消息处理队列


# 获取机器人运行的根目录，用于解析相对路径
BOT_ROOT_PATH = Path().cwd()
# 解析群聊提示词目录的绝对路径
GROUP_PROMPTS_ABSOLUTE_DIR = BOT_ROOT_PATH / group_prompts_dir
# 确保目录存在，如果不存在则创建
try:
    GROUP_PROMPTS_ABSOLUTE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"群聊专属提示词目录已确认为: {GROUP_PROMPTS_ABSOLUTE_DIR}")
except Exception as e:
    logger.error(
        f"创建或确认群聊专属提示词目录失败: {GROUP_PROMPTS_ABSOLUTE_DIR}, 错误: {e}"
    )
    logger.warning("群聊专属提示词功能可能无法正常工作，请检查目录权限或配置。")


def format_reply(reply: str | dict) -> list:
    # 格式化回复消息 (与之前修改版基本一致，确保健壮性)
    result = []

    def process_message(msg_dict):  # 参数名修改避免与外部变量冲突
        msg_type = msg_dict.get("type")
        if msg_type == "text":
            # 纯文本
            return MessageSegment.text(msg_dict.get("content", ""))
        elif msg_type == "at":
            # 艾特
            return MessageSegment.at(msg_dict.get("uid", 0))
        elif msg_type == "poke":
            # 戳一戳
            poke = PokeMessage()
            poke.gid = msg_dict.get("gid", 0)
            poke.uid = msg_dict.get("uid", 0)
            return poke
        elif msg_type == "ban":
            # 禁言
            ban = BanUser()
            ban.gid = msg_dict.get("gid", 0)
            ban.uid = msg_dict.get("uid", 0)
            ban.duration = msg_dict.get("duration", 0)
            return ban
        elif msg_type == "meme":
            # 表情包
            for meme_item in memes:
                if meme_item["url"] == msg_dict.get("url"):
                    url = meme_item["url"]
                    if not url.startswith(("http://", "https://")):
                        url = os.path.abspath(url.replace("\\", "/"))
                        url = f"file:///{url}"
                    return MessageSegment.image(url)
            return MessageSegment.text("[未知表情包 URL]")
        elif msg_type == "tts":
            # 语音合成
            tts = TTSMessage()
            tts.text = msg_dict.get("content", "")
            tts.reference_id = tts_config.reference_id
            return tts
        else:
            return MessageSegment.text(f"[未知消息类型 {msg_type}]")

    if isinstance(reply, str):
        try:
            cleaned_reply = reply.strip()
            if cleaned_reply.startswith("```json"):
                cleaned_reply = cleaned_reply[7:]
            if cleaned_reply.endswith("```"):
                cleaned_reply = cleaned_reply[:-3]
            reply_data = json.loads(cleaned_reply)  # 修改变量名
        except json.JSONDecodeError as e:
            logger.warning(
                f"回复内容JSON解析轻微错误: {e}, 内容片段: {reply[:200]}. 将尝试作为纯文本处理。"
            )
            # 如果解析失败，但原始回复是字符串，则直接返回原始字符串作为文本消息
            return [MessageSegment.text(reply)]
        except Exception as e_gen:  # 其他可能的解析错误
            logger.error(f"回复内容JSON解析严重错误: {e_gen}, 内容片段: {reply[:200]}.")
            return [MessageSegment.text("AI回复的格式我暂时看不懂，呜呜~")]
    elif isinstance(reply, dict):
        reply_data = reply  # 如果已经是dict，直接使用
    else:  # 如果不是str也不是dict，无法处理
        logger.error(f"未知的AI回复类型: {type(reply)}, 内容: {str(reply)[:200]}")
        return [MessageSegment.text("AI的回复有点奇怪，我不知道该怎么展示它。")]

    # 确保 reply_data 是一个字典
    if not isinstance(reply_data, dict):
        logger.warning(
            f"JSON解析后类型不是dict，而是 {type(reply_data)}，将尝试作为纯文本处理原始回复。"
        )
        return [
            (
                MessageSegment.text(str(reply))
                if isinstance(reply, str)
                else MessageSegment.text("AI回复格式异常")
            )
        ]

    messages_list = reply_data.get("messages", [])
    if not isinstance(messages_list, list):  # messages 字段必须是列表
        logger.warning(
            f"AI回复中的 'messages' 字段不是列表，而是 {type(messages_list)}。"
        )
        messages_list = []  # 置为空列表以避免后续错误

    for msg_content in messages_list:
        if isinstance(msg_content, dict):
            result.append(process_message(msg_content))
        elif isinstance(msg_content, list):
            chid_result = OneBotMessage()  # 使用OneBotMessage来组合多个segment
            for chid_msg_dict in msg_content:
                if isinstance(chid_msg_dict, dict):
                    chid_result.append(process_message(chid_msg_dict))
                else:
                    # 对于列表内非字典项，可以考虑记录日志或作为文本处理
                    logger.debug(f"消息列表内发现非字典项: {chid_msg_dict}")
                    chid_result.append(MessageSegment.text(str(chid_msg_dict)))
            if chid_result:
                result.append(chid_result)
        else:
            # 对于 messages 列表下非字典也非列表的项
            logger.debug(f"顶层消息列表内发现未知格式项: {msg_content}")
            result.append(MessageSegment.text(str(msg_content)))

    if not result and isinstance(reply, str):
        return [
            MessageSegment.text(reply)
        ]  # 保底：如果解析后啥也没有，但原始是字符串，就发原始字符串
    elif not result:
        return [MessageSegment.text("AI好像什么都没说呢...")]

    return result


model_choose = on_command(
    cmd="选择模型",
    aliases={"模型选择"},
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER | PRIVATE_FRIEND,
    block=True,
)


@model_choose.handle()
async def _(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    args: Message = CommandArg(),
):  # 使用 nonebot.adapters.Message
    if isinstance(event, GroupMessageEvent):
        perm = GROUP_ADMIN | GROUP_OWNER | SUPERUSER
        if not (await perm(bot, event)):
            await model_choose.finish(
                "你没有权限使用该命令啦~请让管理员来吧", at_sender=True
            )

    if model_arg := args.extract_plain_text().strip():
        id_key = (
            str(event.user_id)
            if isinstance(event, PrivateMessageEvent)
            else str(event.group_id)
        )
        chat_type = "private" if isinstance(event, PrivateMessageEvent) else "group"
        if model_arg not in model_list:
            await model_choose.finish(
                f"你选择的模型 '{model_arg}' 不存在哦！请从可用模型列表中选择。",
                at_sender=True,
            )

        if chat_type not in user_config:
            user_config[chat_type] = {}
        if id_key not in user_config[chat_type]:
            user_config[chat_type][id_key] = {}

        user_config[chat_type][id_key]["model"] = model_arg
        # 切换模型后，清空历史消息，确保system prompt能正确应用
        user_config[chat_type][id_key]["messages"] = []
        await model_choose.finish(
            f"模型已经切换为 {model_arg} 了哦~ 聊天记录已重置以应用新设定。",
            at_sender=True,
        )
    else:
        msg_list_str = "可以使用的模型有这些哦："
        for i in api_list:
            msg_list_str += f"\n{i.name}"
            if i.description:
                msg_list_str += f"\n  - {i.description}"
        msg_list_str += "\n\n请发送 /选择模型 <模型名> 来选择模型哦！"
        await model_choose.finish(msg_list_str, at_sender=True)


# 清空聊天记录
clear_history = on_command(
    cmd="清空聊天记录",
    aliases={"清空对话"},
    permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | PRIVATE_FRIEND,
    block=True,
)


@clear_history.handle()
async def _(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    if isinstance(event, GroupMessageEvent):
        perm = GROUP_ADMIN | GROUP_OWNER | SUPERUSER
        if not (await perm(bot, event)):
            await clear_history.finish(
                "你没有权限使用该命令啦~请让管理员来吧", at_sender=True
            )

    id_key = (
        str(event.user_id)
        if isinstance(event, PrivateMessageEvent)
        else str(event.group_id)
    )
    chat_type = "private" if isinstance(event, PrivateMessageEvent) else "group"

    if user_config.get(chat_type, {}).get(id_key):
        user_config[chat_type][id_key]["messages"] = []
    await clear_history.finish("本轮对话记录已清空～", at_sender=True)


switch_cmd = on_command(  # 命令名修改，避免与python关键字switch冲突
    cmd="ai对话", aliases={"切换ai对话"}, permission=GROUP | PRIVATE_FRIEND, block=True
)


@switch_cmd.handle()
async def _(
    bot: Bot,
    event: GroupMessageEvent | PrivateMessageEvent,
    args: Message = CommandArg(),
):
    if isinstance(event, GroupMessageEvent):
        perm = GROUP_ADMIN | GROUP_OWNER | SUPERUSER
        if not (await perm(bot, event)):
            await switch_cmd.finish(
                "你没有权限使用该命令啦~请让管理员来吧", at_sender=True
            )

    if arg_text := args.extract_plain_text().strip():  # 变量名修改
        id_val = (
            event.user_id if isinstance(event, PrivateMessageEvent) else event.group_id
        )
        if arg_text == "开启":
            (
                enable_private(id_val)
                if isinstance(event, PrivateMessageEvent)
                else enable(id_val)
            )
            await switch_cmd.finish("AI对话已经开启~", at_sender=True)
        elif arg_text == "关闭":
            (
                disable_private(id_val)
                if isinstance(event, PrivateMessageEvent)
                else disable(id_val)
            )
            await switch_cmd.finish("AI对话已经禁用~", at_sender=True)
        else:
            await switch_cmd.finish(
                "请使用 /ai对话 <开启/关闭> 来操作哦~", at_sender=True
            )
    else:
        await switch_cmd.finish(
            "请使用 /ai对话 <开启/关闭> 来开启或关闭本群/私聊的AI对话功能~",
            at_sender=True,
        )


# 处理群聊消息
handler = on_message(
    rule=Rule(
        lambda event: isinstance(event, GroupMessageEvent)
        and event.get_plaintext().startswith(command_start)  # 使用配置的触发前缀
        and event.to_me  # 需要艾特机器人
        and is_available(event.group_id)  # 检查群功能是否开启
    ),
    permission=GROUP,
    priority=50,
    block=False,  # block=False 允许其他插件处理
)
# 处理私聊消息
handler_private = on_message(
    rule=Rule(
        lambda event: isinstance(event, PrivateMessageEvent)
        and is_private_available(event.user_id)  # 检查私聊功能是否开启
    ),
    permission=PRIVATE_FRIEND,
    priority=50,
    block=False,
)


@handler.handle()
@handler_private.handle()
async def _(event: GroupMessageEvent | PrivateMessageEvent, bot: Bot):
    id_key = (
        str(event.user_id)
        if isinstance(event, PrivateMessageEvent)
        else str(event.group_id)
    )
    chat_type = "private" if isinstance(event, PrivateMessageEvent) else "group"

    # 忽略特定QQ号的消息，例如Q群管家
    if isinstance(event, GroupMessageEvent) and str(event.user_id) in [
        "2854196310"
    ]:  # 可以配置化
        return

    if not check_cd(id_key):  # 检查CD
        # 可以选择发送消息或静默处理
        # await handler.finish("你的操作太频繁了哦！请稍后再试！", at_sender=True)
        logger.debug(f"用户 {event.user_id} 操作过于频繁，CD中。")
        return

    # 初始化用户/群聊配置（如果不存在）
    if chat_type not in user_config:
        user_config[chat_type] = {}
    if id_key not in user_config[chat_type]:
        user_config[chat_type][id_key] = {}

    if "model" not in user_config[chat_type][id_key]:
        await handler.send(
            "你还没有选择AI模型哦，请先使用 /选择模型 <模型名> 来选择一个模型吧！",
            at_sender=True,
        )
        return  # 使用 send 而不是 finish，避免阻塞其他消息处理

    if id_key in sequence[chat_type]:  # 检查是否已有消息在处理
        await handler.send("不要着急哦！我还在思考上一条消息呢...", at_sender=True)
        return

    images_base64 = []  # 存储图片base64数据

    # 尝试设置输入状态 (onebot v11可能不支持或实现各异)
    # if isinstance(event, PrivateMessageEvent):
    #     try:
    #         await bot.set_typing(user_id=event.user_id) # 假设有此API
    #     except Exception as ex:
    #         logger.debug(f"设置私聊输入状态失败: {str(ex)}")

    api_key_val = ""
    api_url_val = ""
    model_name_val = ""
    send_thinking_enabled = False  # 变量名修改
    selected_model_config = None

    for model_conf_item in api_list:  # 变量名修改
        if model_conf_item.name == user_config[chat_type][id_key]["model"]:
            selected_model_config = model_conf_item
            api_key_val = model_conf_item.api_key
            api_url_val = model_conf_item.api_url
            model_name_val = model_conf_item.model_name
            send_thinking_enabled = model_conf_item.send_thinking
            if model_conf_item.image_input:  # 如果模型支持图片输入
                # --- 修改调用 get_images 的地方，传入 bot ---
                images_base64 = await get_images(event, bot)
            break

    if not selected_model_config:
        logger.error(
            f"无法找到模型 {user_config[chat_type][id_key]['model']} 的配置信息。"
        )
        await handler.send(
            "哎呀，选中的模型配置好像不见了，请联系管理员检查下。", at_sender=True
        )
        return

    # 初始化或加载聊天记录和系统提示词
    if (
        "messages" not in user_config[chat_type][id_key]
        or not user_config[chat_type][id_key]["messages"]
    ):
        memes_msg_list_str = f"url - 描述"
        for meme_item in memes:
            memes_msg_list_str += (
                f"\n            {meme_item['url']} - {meme_item['desc']}"
            )

        # --- 核心修改：加载提示词逻辑 ---
        character_prompt_content = None  # 变量名修改

        # 1. 尝试加载群聊专属提示词 (仅群聊)
        if chat_type == "group":
            group_prompt_file_path = GROUP_PROMPTS_ABSOLUTE_DIR / f"{id_key}.txt"
            if group_prompt_file_path.exists() and group_prompt_file_path.is_file():
                try:
                    character_prompt_content = group_prompt_file_path.read_text(
                        encoding="utf-8"
                    ).strip()
                    if character_prompt_content:
                        logger.info(
                            f"群聊 {id_key} 加载专属提示词文件: {group_prompt_file_path}"
                        )
                    else:
                        logger.warning(
                            f"群聊 {id_key} 的专属提示词文件 {group_prompt_file_path} 为空。"
                        )
                        character_prompt_content = None  # 文件为空则视为无效
                except Exception as e:
                    logger.error(
                        f"读取群聊 {id_key} 专属提示词文件 {group_prompt_file_path} 失败: {e}"
                    )
                    character_prompt_content = None  # 读取失败则视为无效
            else:
                logger.debug(
                    f"群聊 {id_key} 未找到专属提示词文件: {group_prompt_file_path}"
                )

        # 2. 如果没有群专属提示词 (或非群聊，或群文件加载失败/为空)，尝试加载全局默认提示词文件
        if character_prompt_content is None and default_prompt_file:
            default_prompt_file_path = BOT_ROOT_PATH / default_prompt_file.replace(
                "\\\\", os.sep
            ).replace("\\", os.sep)
            if default_prompt_file_path.exists() and default_prompt_file_path.is_file():
                try:
                    character_prompt_content = default_prompt_file_path.read_text(
                        encoding="utf-8"
                    ).strip()
                    if character_prompt_content:
                        logger.info(
                            f"加载全局默认提示词文件: {default_prompt_file_path}"
                        )
                    else:
                        logger.warning(
                            f"全局默认提示词文件 {default_prompt_file_path} 为空。"
                        )
                        character_prompt_content = None
                except Exception as e:
                    logger.error(
                        f"读取全局默认提示词文件 {default_prompt_file_path} 失败: {e}"
                    )
                    character_prompt_content = None
            else:
                logger.warning(
                    f"配置的全局默认提示词文件未找到: {default_prompt_file_path}"
                )

        # 3. 如果以上均未成功加载，则使用配置中的默认字符串提示词
        if character_prompt_content is None:
            character_prompt_content = (
                default_prompt  # 使用 config.py 中定义的 default_prompt
            )
            logger.info(f"使用内置默认提示词 (来自aitalk_default_prompt配置)。")

        if (
            not character_prompt_content
        ):  # 最终检查，如果提示词内容为空，给一个非常基础的默认值
            character_prompt_content = "你是一个乐于助人的AI助手。"
            logger.warning("所有提示词来源均为空或加载失败，使用最基础的默认提示词。")
        # --- 提示词加载逻辑结束 ---

        bot_nicknames = (
            list(driver.config.nickname)
            if driver.config.nickname
            else [str(bot.self_id)]
        )

        system_prompt_text = f"""
我需要你在群聊中进行闲聊。大家通常会称呼你为{"、".join(bot_nicknames)}。我会在后续信息中告诉你每条群聊消息的发送者和发送时间，你可以直接称呼发送者为他们的昵称。

你的回复需要遵守以下规则：
- 不要使用 Markdown 或 HTML 格式。聊天软件不支持解析，换行请用换行符。
- 以普通人的口吻发送消息，每条消息尽量简短，可以分多条回复，但请控制在 {max_split_length} 条消息以内。
- 如果需要发送代码，请用单独的一条消息发送，不要分段。
- 使用发送者的昵称称呼对方。第一次回复时可以礼貌问候，但后续无需重复问候。
- 如果需要思考，直接用普通文本表达，不要用 JSON 格式。
- 不要在思考内容中提到 JSON 或其他格式要求。

以下是你的性格设定，如果设定中提到让你扮演某个人或有名字，则优先使用设定中的名字：
{character_prompt_content}
你的正文回复需要统一使用 JSON 格式，所有回复内容将包裹在一个字典里。字典中的 `messages` 字段代表你的回复，你还可以根据情景向字典里添加其他参数。可用的参数如下：
- `reply`：布尔值，是否回复用户的消息。如果是回复，请在 `msg_id` 字段内填入消息 ID。注意:私聊消息请不要回复。
- `messages` 字段是一个列表，你可以向里面添加字典或列表：
  - 如果是列表，则代表列表中的所有内容为一句话。
  - 如果是字典，则代表一句话。
- 字典中的 `type` 字段代表类型，可用的值有：
  - `at`：艾特某人，需要在 `uid` 字段中填入要艾特的用户 ID。艾特发送者不是必须的,你可以根据需要艾特某个人。
  - `text`：纯文本消息，需要在 `content` 字段中填入内容。
  - `poke`：发送戳一戳，需要在 `uid` 字段中填入用户 ID,并在 `gid` 字段中填入群号。
  - `meme`：图片表情包，需要在 `url` 字段中填入表情包的 URL。
  - `ban`：禁言用户,在 `uid` 字段中填入用户 ID,并在 `gid` 字段中填入群号,同时在 `duration` 字段中填入禁言时间;
    当你想要调戏用户、活跃气氛、或认为需要对用户适当惩罚时等情景可以使用,此情景禁言时间需控制在60以内;
    若用户发送了含有政治、色情、辱骂等违禁词时,应当使用更严厉更激进的禁言时间,例如1800(30分钟)或3600(1小时)甚至更长。
  {'- `tts`：语音合成，发送语音消息，需要在 `content` 字段中填入说话内容。' if tts_enabled else ''}

可用的表情包列表：
{memes_msg_list_str}

请注意以下几点：
- 请按照场景灵活使用参数。
- 不要在回复中使用任何其他符号。
- 不要说明回复的是 JSON 格式，直接输出 JSON 字符串即可。

示例如下：
```json
{{
    "messages": [ 
        [ 
            {{ "type": "at", "uid": "1111111" }},
            {{ "type": "text", "content": "中午好呀≡ (^(OO)^) ≡ ，有什么我可以帮你的吗" }}
        ],
        {{ "type": "text", "content": "今天的天气很好哦，要不要出去走一走呢～" }},
        {{ "type": "meme", "url": "表情包URL" }},
        {{ "type": "poke", "uid": "11111", "gid": "1111111" }},
        {{ "type": "ban", "uid": "11111", "gid": "1111111", "duration": 8 }}
        {'- {{ "type": "tts", "content": "有什么我可以帮你的吗？" }}' if tts_enabled else ''}
    ],
    "reply": true,
    "msg_id": "1234567890"
}}
```
        """
        user_config[chat_type][id_key]["messages"] = [
            {"role": "system", "content": system_prompt_text}
        ]

    # 用户信息
    user_prompt_text = f"""
    - 用户昵称：{event.sender.nickname}
    - 用户QQ号: {event.user_id}
    - 消息时间：{time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(event.time))}
    - 消息id: {str(event.message_id)}
    - 群号: {str(event.group_id) if isinstance(event,GroupMessageEvent) else "这是一条私聊消息"}
    - 用户说：{event.get_plaintext()}
    """

    # 上下文长度管理
    if len(user_config[chat_type][id_key]["messages"]) >= max_context_length:
        # 保留system prompt (第一条)，然后保留最新的 N-1 条对话记录
        system_message = user_config[chat_type][id_key]["messages"][0]
        recent_messages = user_config[chat_type][id_key]["messages"][
            -(max_context_length - 2) :
        ]  # 保留 N-2 条，因为要加入新的user message
        user_config[chat_type][id_key]["messages"] = [system_message] + recent_messages

    # 构建用户消息内容 (文本 + 图片)
    user_message_content_list = [{"type": "text", "text": user_prompt_text}]
    if images_base64:
        for img_b64 in images_base64:
            user_message_content_list.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                }
            )

    user_config[chat_type][id_key]["messages"].append(
        {"role": "user", "content": user_message_content_list}
    )

    try:
        sequence[chat_type].append(id_key)  # 加入处理队列

        # 从AI处获取回复
        reply_content_str, thinking_content_str, success, err_msg = await gen(
            user_config[chat_type][id_key]["messages"],
            model_name_val,
            api_key_val,
            api_url_val,
        )

        if not success:
            await handler.send(err_msg)
            
            if user_config[chat_type][id_key]["messages"][-1].get("role") == "user":
                user_config[chat_type][id_key]["messages"].pop()  # 移除对应的user消息

        logger.debug(
            f"AI原始回复 ({chat_type} {id_key}): {str(reply_content_str)[:500]}..."
        )  # 日志截断

        if reply_content_str is None:
            raise ValueError("AI未能生成回复内容 (返回None)。")

        user_config[chat_type][id_key]["messages"].append(
            {"role": "assistant", "content": f"{reply_content_str}"}
        )

        if send_thinking_enabled and thinking_content_str:
            await send_thinking_msg(
                bot,
                event,
                thinking_content_str,
                list(driver.config.nickname) if driver.config.nickname else [],
            )

        formatted_reply_list = format_reply(reply_content_str)  # 变量名修改
        should_reply_flag, original_msg_id_val = need_reply_msg(
            reply_content_str, event
        )  # 变量名修改

        await send_formatted_reply(
            bot, event, formatted_reply_list, should_reply_flag, original_msg_id_val
        )
        add_cd(id_key)  # 添加CD

    except Exception as e:
        # 发生错误时，从历史记录中移除最后一条用户消息（如果已添加）和可能的AI消息（如果已添加）
        # 简化处理：只移除最后一条，通常是用户的提问，避免污染上下文
        if user_config.get(chat_type, {}).get(id_key, {}).get("messages"):
            if (
                user_config[chat_type][id_key]["messages"][-1].get("role")
                == "assistant"
            ):
                user_config[chat_type][id_key][
                    "messages"
                ].pop()  # 移除错误的assistant消息
            if user_config[chat_type][id_key]["messages"][-1].get("role") == "user":
                user_config[chat_type][id_key]["messages"].pop()  # 移除对应的user消息

        error_message_text = (
            f"哎呀，AI思考的时候好像出了点小问题！\n错误摘要：{str(e)[:100]}"
        )
        logger.error(
            f"AI处理出错 ({chat_type} {id_key}): {e}", exc_info=True
        )  # exc_info=True 会记录完整的traceback
        await handler.send(error_message_text, reply_message=True)
    finally:
        if id_key in sequence[chat_type]:  # 确保从队列中移除
            sequence[chat_type].remove(id_key)


# 定义启动时的钩子函数，用于读取用户配置 (例如模型选择等，不包括聊天记录本身)
@driver.on_startup
async def _():
    if save_user_config:
        global user_config
        saved_data = read_all_data()  # data.py 中的函数
        if saved_data:
            # 只恢复模型选择等配置，不恢复 "messages" 历史记录
            # "messages" 应该在每次对话开始时基于当前提示词重新构建system prompt
            for chat_type in ["private", "group"]:
                if chat_type in saved_data:
                    user_config[chat_type] = {}
                    for id_key, config_data in saved_data[chat_type].items():
                        user_config[chat_type][id_key] = {}
                        if "model" in config_data:
                            user_config[chat_type][id_key]["model"] = config_data[
                                "model"
                            ]
                        # 不加载 "messages" 或 "prompt" (prompt来自文件)
            logger.info(
                "用户运行时配置 (如模型选择) 已从本地加载。聊天记录和提示词将按需生成。"
            )
        else:
            user_config = {"private": {}, "group": {}}  # 重置为空
            logger.info("未找到用户运行时配置文件或文件为空，使用默认空配置。")


# 定义关闭时的钩子函数，用于保存用户配置 (例如模型选择)
@driver.on_shutdown
async def _():
    if save_user_config:
        global user_config
        data_to_save = {"private": {}, "group": {}}
        for chat_type in ["private", "group"]:
            if chat_type in user_config:
                data_to_save[chat_type] = {}
                for id_key, config_data in user_config[chat_type].items():
                    data_to_save[chat_type][id_key] = {}
                    if "model" in config_data:
                        data_to_save[chat_type][id_key]["model"] = config_data["model"]
                    # 不保存 "messages" 历史记录或 "prompt"

        write_all_data(data_to_save)  # data.py 中的函数
        logger.info("用户运行时配置 (如模型选择) 已保存。")
