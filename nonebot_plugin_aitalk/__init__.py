import os
from openai import AsyncOpenAI
from pathlib import Path  # 引入 Path
from nonebot import on_message, on_command, get_driver, require, logger
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.permission import SUPERUSER
from nonebot.adapters import Message  # Message 类型用于 CommandArg
from nonebot.params import CommandArg, EventPlainText  # 显式导入 EventPlainText
from nonebot.typing import T_State  # 导入 T_State
from nonebot.exception import IgnoredException  # 导入 IgnoredException

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

require("nonebot_plugin_localstore")  # 确保本地存储插件已加载

import json, time, random, re  # 导入 re
from .config import *  # 导入所有配置
from .api import gen  # 从 api.py 导入 gen 函数
from .data import *  # 从 data.py 导入数据处理函数
from .cd import *  # 从 cd.py 导入CD处理函数
from .utils import *  # 从 utils.py 导入工具函数
from .msg_seg import *  # 从 msg_seg.py 导入消息段定义 (如果实际有用到的话)


__plugin_meta__ = PluginMetadata(
    name="简易AI聊天",
    description="简单好用的AI聊天插件。支持多API、图片理解、语音合成、表情包、提醒、戳一戳等。群聊提示词通过在指定目录创建 {GROUP_ID}.txt 文件进行配置。拥有主动回复功能。",  # 更新描述
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
    supported_adapters={"~onebot.v11"},  # 支持的适配器
)

driver = get_driver()  # 获取 NoneBot Driver 对象

# 用户运行时配置，用于存储模型选择、聊天记录等状态
user_config = {
    "private": {},  # 私聊配置
    "group": {},  # 群聊配置
}
memes = [dict(i) for i in available_memes]  # 加载可用表情包列表
model_list = [i.name for i in api_list]  # 加载可用模型名称列表
sequence = {"private": [], "group": []}  # 消息处理队列，防止并发处理同一用户的消息

# 主动回复上下文会话信息
# 结构: {group_id: {"last_bot_reply_time": float, "original_user_msg_id": str, "last_interaction_time": float, "unrelated_followup_count": int}}
active_reply_sessions = {}


# 获取机器人运行的根目录，用于解析相对路径
BOT_ROOT_PATH = Path().cwd()
# 解析群聊提示词目录的绝对路径
GROUP_PROMPTS_ABSOLUTE_DIR = BOT_ROOT_PATH / group_prompts_dir
# 确保目录存在，如果不存在则创建
try:
    GROUP_PROMPTS_ABSOLUTE_DIR.mkdir(
        parents=True, exist_ok=True
    )  # 创建目录，如果父目录不存在也一并创建
    logger.info(f"群聊专属提示词目录已确认为: {GROUP_PROMPTS_ABSOLUTE_DIR}")
except Exception as e:
    logger.error(
        f"创建或确认群聊专属提示词目录失败: {GROUP_PROMPTS_ABSOLUTE_DIR}, 错误: {e}"
    )
    logger.warning("群聊专属提示词功能可能无法正常工作，请检查目录权限或配置。")


# --- 尝试修复JSON的辅助函数 ---
async def try_fix_json_with_ai(
    malformed_json: str, original_model_config: ModelConfig
) -> str | None:
    """
    尝试使用AI模型修复格式错误的JSON字符串。
    这是一个临时的、隔离的AI调用，不会影响主对话历史。

    :param malformed_json: 格式错误的JSON字符串。
    :param original_model_config: 用于生成原始回复的模型配置，将用于修复尝试。
    :return: 修复后的JSON字符串，如果修复成功且有效；否则返回None。
    """
    logger.info(
        f"尝试使用AI修复错误的JSON格式: {malformed_json[:100]}..."
    )  # 日志记录，截断过长JSON

    # 修复用的 System Prompt，指导AI如何修正JSON
    fixer_system_prompt = """
你是一个JSON修复助手。你会收到一个可能格式错误的JSON字符串，或收到一个带有额外说明的不纯净的JSON字符串。
你的任务是尽力将其修正为一个结构正确的JSON字符串，如果带有额外说明，需要将其删除，并确保它符合以下原始AI期望输出的格式：
```json
{
    "messages": [ 
        [ 
            { "type": "at", "uid": "1111111" },
            { "type": "text", "content": "一些文本" }
        ],
        { "type": "text", "content": "其他文本" },
        { "type": "meme", "url": "图片URL" }
    ],
    "reply": true, // 或 false
    "msg_id": "消息ID", // 可选
    "should_reply": true // 或 false, 主要用于主动回复判断
}
```
请只输出修正后的JSON字符串，不要包含任何额外的解释或Markdown标记。
如果无法修复，或者输入内容与JSON无关，请返回原始输入。
"""
    # 构建发送给AI的修复请求消息列表
    repair_messages = [
        {"role": "system", "content": fixer_system_prompt},
        {"role": "user", "content": malformed_json},  # 将损坏的JSON作为用户消息发送
    ]

    try:
        # 使用与原始对话相同的模型配置进行修复尝试
        # 为修复任务调整生成参数，例如较低的temperature使输出更确定
        temp_completion_config = CompletionConfig(
            max_token=1024, temperature=0.2, top_p=0.9
        )

        # 创建临时的OpenAI客户端进行调用
        client = AsyncOpenAI(
            base_url=original_model_config.api_url,
            api_key=original_model_config.api_key,
        )
        completion = await client.chat.completions.create(
            model=original_model_config.model_name,  # 使用原始模型
            messages=repair_messages,
            max_tokens=temp_completion_config.max_token,
            temperature=temp_completion_config.temperature,
            top_p=temp_completion_config.top_p,
        )
        fixed_json_str = completion.choices[0].message.content  # 获取AI修复后的内容
        if fixed_json_str:
            # 尝试再次解析修复后的JSON，验证其有效性
            try:
                json.loads(fixed_json_str.strip())
                logger.info(f"AI修复JSON成功: {fixed_json_str[:100]}...")
                return fixed_json_str.strip()  # 返回清理首尾空白后的修复结果
            except json.JSONDecodeError:
                logger.warning(f"AI修复后的JSON仍然无效: {fixed_json_str[:100]}...")
                return None  # 修复后仍然是无效JSON
        else:
            logger.warning("AI修复JSON未返回任何内容。")
            return None  # AI未返回任何修复内容
    except Exception as e:
        logger.error(f"AI修复JSON过程中发生错误: {e}")
        return None  # 修复过程中发生异常


# 修改 format_reply 以支持主动回复检查和JSON修复
async def format_reply(
    reply: str | dict,
    for_active_check: bool = False,
    model_config_for_repair: ModelConfig | None = None,
) -> list | tuple[bool, list]:
    """
    格式化AI的回复。
    如果AI回复是字符串形式的JSON，则解析它。
    如果解析失败，并且提供了 model_config_for_repair，则尝试使用AI修复JSON。
    根据 for_active_check 标志，处理主动回复的判断逻辑。

    :param reply: AI的原始回复 (字符串或字典)。
    :param for_active_check: 是否为主动回复的判断场景。
    :param model_config_for_repair: 用于JSON修复的模型配置。
    :return: 如果 for_active_check 为 True，返回 (bool, list)，分别表示是否应回复及消息列表。
             否则返回消息列表 list。
    """
    result = []  # 存储最终格式化的消息段列表
    should_active_reply = False  # 主动回复的判断结果，默认为False
    attempted_json_fix = False  # 标记是否已尝试过JSON修复

    def process_message(msg_dict):  # 辅助函数，将单个消息字典转换为MessageSegment
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
                        url = f"file:///{os.path.abspath(url.replace(os.sep, '/'))}"  # 修正路径处理
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

    reply_data = {}  # 用于存储解析后的JSON数据

    if isinstance(reply, str):  # 如果AI回复是字符串
        try:
            # 清理常见的代码块标记
            cleaned_reply = reply.strip()
            if cleaned_reply.startswith("```json"):
                cleaned_reply = cleaned_reply[7:]
            if cleaned_reply.endswith("```"):
                cleaned_reply = cleaned_reply[:-3]
            reply_data = json.loads(cleaned_reply)  # 尝试解析JSON
        except json.JSONDecodeError as e:  # JSON解析失败
            logger.warning(
                f"回复内容JSON解析错误: {e}, 内容片段: {reply[:100]}."
            )  # 减少日志长度
            if (
                model_config_for_repair and not attempted_json_fix
            ):  # 如果允许修复且未尝试过
                attempted_json_fix = True  # 标记已尝试
                logger.info("将尝试使用AI修复JSON...")
                fixed_json_str = await try_fix_json_with_ai(
                    reply, model_config_for_repair
                )  # 调用修复函数
                if fixed_json_str:
                    try:
                        reply_data = json.loads(fixed_json_str)  # 尝试解析修复后的JSON
                        logger.info("AI修复后的JSON解析成功。")
                    except json.JSONDecodeError as e_fixed:
                        logger.error(
                            f"AI修复后的JSON仍然解析失败: {e_fixed}, 内容: {fixed_json_str[:100]}"
                        )
                        err_msg_list = [
                            MessageSegment.text("AI回复的格式有点奇怪，我修复失败了~")
                        ]
                        if for_active_check:
                            return False, err_msg_list
                        return err_msg_list
                else:  # AI修复未返回有效内容
                    logger.warning("AI修复JSON未返回有效结果。")
                    err_msg_list = [
                        MessageSegment.text("AI回复的格式有点问题，而且我没能修好它。")
                    ]
                    if for_active_check:
                        return False, err_msg_list
                    return err_msg_list
            else:  # 不进行修复或修复已失败/未提供修复配置
                err_msg_list = [
                    MessageSegment.text("AI回复的格式似乎有点问题。")
                ]  # 发送通用错误提示
                if for_active_check:
                    return False, err_msg_list
                return err_msg_list
        except Exception as e_gen:  # 其他可能的未知错误
            logger.error(f"处理AI回复时发生未知错误: {e_gen}, 内容片段: {reply[:100]}.")
            err_msg_list = [MessageSegment.text("处理AI回复时发生了一个内部错误。")]
            if for_active_check:
                return False, err_msg_list
            return err_msg_list
    elif isinstance(reply, dict):  # 如果AI回复直接是字典
        reply_data = reply
    else:  # 如果AI回复既不是字符串也不是字典
        logger.error(f"未知的AI回复类型: {type(reply)}, 内容: {str(reply)[:100]}")
        err_msg_list = [MessageSegment.text("AI的回复格式无法识别。")]
        if for_active_check:
            return False, err_msg_list
        return err_msg_list

    # 到这里，reply_data 应该是一个解析成功的字典
    if not isinstance(reply_data, dict):  # 双重检查，理论上不应执行到这里
        logger.error(
            f"内部逻辑错误：reply_data 未能正确处理为字典。"
        )  # 记录更严重的错误
        err_msg_list = [MessageSegment.text("插件内部处理AI回复时出错。")]
        if for_active_check:
            return False, err_msg_list
        return err_msg_list

    # 如果是主动回复的判断场景，解析 "should_reply" 字段
    if for_active_check:
        should_active_reply = reply_data.get("should_reply", False)  # 默认为False
        if not should_active_reply:  # 如果AI明确指示不回复
            logger.debug(f"主动回复检查：AI指示 should_reply=false。")
            return False, []  # 直接返回不回复和空消息列表

    # 获取 "messages" 字段，它应该是一个列表
    messages_list = reply_data.get("messages", [])
    if not isinstance(messages_list, list):
        logger.warning(
            f"AI回复中的 'messages' 字段不是列表，实际类型: {type(messages_list)}。"
        )
        messages_list = []  # 安全起见，置为空列表

    # 处理 messages 列表中的每个消息项
    for msg_content in messages_list:
        if isinstance(msg_content, dict):  # 单个消息段
            result.append(process_message(msg_content))
        elif isinstance(msg_content, list):  # 多个消息段组成一条消息
            chid_result = OneBotMessage()
            for chid_msg_dict in msg_content:
                if isinstance(chid_msg_dict, dict):
                    chid_result.append(process_message(chid_msg_dict))
                else:
                    logger.debug(f"内部消息列表发现非字典项: {chid_msg_dict}")
                    chid_result.append(MessageSegment.text(str(chid_msg_dict)))
            if chid_result:
                result.append(chid_result)  # 添加组合后的消息
        else:  # messages 列表中包含非字典也非列表的项
            logger.debug(f"顶层消息列表发现未知格式项: {msg_content}")
            result.append(MessageSegment.text(str(msg_content)))  # 作为纯文本处理

    # 返回最终结果
    if for_active_check:
        # 对于主动回复判断，即使 should_active_reply 为 True，如果 result 为空，也应视为不回复或回复空内容
        # 但通常AI在 should_active_reply=True 时会给出 messages 内容
        return should_active_reply, result
    else:  # 正常对话场景
        if not result and isinstance(reply, str) and not attempted_json_fix:
            # 保底：如果解析后无内容，原始是字符串，且未尝试过修复（说明不是JSON格式错误而是AI就没按JSON返回）
            # 这种情况比较少见，通常AI会返回JSON或纯文本。
            # 如果AI返回了非JSON的纯文本，上面的 try-except 会捕获并尝试修复或报错。
            # 此处逻辑主要是针对非常规的、非JSON字符串回复。
            # 但由于JSON修复逻辑的存在，此分支实际执行概率较低。
            # 为安全，如果AI返回的纯文本不是JSON，并且我们没有尝试修复它，就直接发送这个纯文本。
            # 但如果尝试修复过（意味着它看起来像JSON但解析失败），则不应再发送原始文本。
            logger.info("AI回复为非JSON字符串且未尝试修复，将作为纯文本发送。")
            return [MessageSegment.text(reply)]
        elif not result:  # 如果最终结果为空列表 (例如AI在追问场景判断不回复)
            return []  # 返回空列表，上层逻辑会判断不发送
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
):
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

    if chat_type == "group" and id_key in active_reply_sessions:
        del active_reply_sessions[id_key]
        logger.info(f"群聊 {id_key} 的主动回复上下文已因清空聊天记录而清除。")

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


async def at_me_rule(bot: Bot, event: GroupMessageEvent) -> bool:
    """匹配 @机器人 或以特定命令前缀开始的群聊消息的规则。"""
    if not (isinstance(event, GroupMessageEvent) and is_available(event.group_id)):
        return False  # 非群聊或群聊AI未启用

    is_at_me = event.to_me  # 是否艾特了机器人
    msg_text = event.get_plaintext()
    is_command_prefix = False
    if command_start:  # 如果配置了命令起始符
        if isinstance(command_start, str) and msg_text.startswith(command_start):
            is_command_prefix = True
        elif isinstance(command_start, list) and any(
            msg_text.startswith(cs) for cs in command_start
        ):
            is_command_prefix = True  # 支持列表形式的命令起始符

    return is_at_me or is_command_prefix  # 任一条件满足即可


async def active_reply_trigger_rule(
    bot: Bot, event: GroupMessageEvent, state: T_State
) -> bool:
    """主动回复的触发规则：判断是否应该对当前群聊消息进行初次主动回复的意图检测。"""
    # 检查总开关、是否为群聊、群聊AI是否启用
    if not (
        active_reply_enabled
        and isinstance(event, GroupMessageEvent)
        and is_available(event.group_id)
    ):
        return False
    # 不响应机器人自身的消息
    if str(event.user_id) == str(bot.self_id):
        return False
    # 如果是艾特机器人的消息，由主handler处理，不由主动回复逻辑处理
    if event.to_me:
        return False

    msg_text = event.get_plaintext().strip()  # 获取纯文本消息并去除首尾空白
    has_image = any(
        seg.type == "image" for seg in event.message
    )  # 检查消息中是否包含图片

    # 如果消息既没有文本内容也没有图片，则忽略
    if not msg_text and not has_image:
        return False

    # 关键词匹配逻辑 (仅对文本内容进行)
    keyword_matched = False
    if msg_text and active_reply_keywords:  # 仅当配置了关键词且消息中有文本时
        for keyword in active_reply_keywords:
            if keyword.lower() in msg_text.lower():  # 不区分大小写匹配
                keyword_matched = True
                break  # 匹配到一个即可

    # 根据是否匹配到关键词，应用不同的概率判断
    trigger_by_probability = False
    if keyword_matched:  # 如果匹配到关键词
        if random.random() < active_reply_probability:
            trigger_by_probability = True
            # logger.debug(f"主动回复规则：消息含关键词，通过概率 ({active_reply_probability})。") # 精简日志
        else:
            # logger.debug(f"主动回复规则：消息含关键词，未通过概率 ({active_reply_probability})。")
            return False  # 未达到关键词概率，不触发
    else:  # 未匹配到关键词 (或关键词列表为空，或消息为纯图片)
        if (
            active_reply_no_keyword_probability > 0
            and random.random() < active_reply_no_keyword_probability
        ):
            trigger_by_probability = True
            # logger.debug(f"主动回复规则：消息无关键词/纯图，通过无关键词概率 ({active_reply_no_keyword_probability})。")
        else:
            # logger.debug(f"主动回复规则：消息无关键词/纯图，未通过无关键词概率 ({active_reply_no_keyword_probability}) 或概率为0。")
            return False  # 未达到无关键词概率或概率为0，不触发

    if not trigger_by_probability:  # 双重保险，理论上不会执行到这里
        return False

    # 检查当前群聊是否已存在一个活跃的主动回复会话
    group_id_str = str(event.group_id)
    if group_id_str in active_reply_sessions:
        session_data = active_reply_sessions[group_id_str]
        # 如果会话存在且未超时，则不应再次触发新的“初次”主动回复，让追问逻辑处理
        if (
            time.time() - session_data.get("last_interaction_time", 0)
            < active_reply_context_timeout
        ):
            # logger.debug(f"主动回复规则：群聊 {group_id_str} 已有活跃会话，不重复触发初判。")
            return False
        else:  # 如果会话已超时，则清理掉旧会话，允许新的主动回复判断
            logger.info(
                f"主动回复规则：群聊 {group_id_str} 的旧主动回复会话已超时，已清理。"
            )
            del active_reply_sessions[group_id_str]

    # logger.debug(f"主动回复规则：消息满足触发条件，设置state['is_active_reply_check']=True。")
    state["is_active_reply_check"] = True  # 标记此事件应由主动回复初判逻辑处理
    return True  # 规则通过


async def active_reply_context_rule(
    bot: Bot, event: GroupMessageEvent, state: T_State
) -> bool:
    """主动回复的上下文追问规则：判断当前群聊消息是否是对机器人先前主动回复的追问。"""
    # 检查总开关、是否为群聊、群聊AI是否启用
    if not (
        active_reply_enabled
        and isinstance(event, GroupMessageEvent)
        and is_available(event.group_id)
    ):
        return False
    # 不响应机器人自身的消息
    if str(event.user_id) == str(bot.self_id):
        return False
    # 如果是艾特机器人的消息，由主handler处理
    if event.to_me:
        return False

    msg_text = event.get_plaintext().strip()
    has_image = any(seg.type == "image" for seg in event.message)

    # 如果消息既没有文本内容也没有图片，则忽略
    if not msg_text and not has_image:
        return False

    group_id_str = str(event.group_id)
    # 检查是否存在当前群聊的主动回复会话
    if group_id_str not in active_reply_sessions:
        return False  # 没有会话，不是追问

    session_data = active_reply_sessions[group_id_str]
    # 检查会话是否已超时 (基于最后互动时间)
    if (
        time.time() - session_data.get("last_interaction_time", 0)
        > active_reply_context_timeout
    ):
        logger.info(f"主动回复追问规则：群聊 {group_id_str} 的主动回复会话已超时。")
        del active_reply_sessions[group_id_str]  # 清理超时会话
        return False  # 超时，不再视为追问

    # logger.debug(f"主动回复追问规则：消息被识别为潜在追问，设置state['is_active_reply_context']=True。")
    state["is_active_reply_context"] = True  # 标记此事件应由主动回复追问逻辑处理
    return True  # 规则通过


# --- Matcher 定义 ---
# 1. 处理 @机器人 或特定命令前缀的群聊消息 (优先级最高)
handler = on_message(
    rule=at_me_rule,
    permission=GROUP,
    priority=10,
    block=True,  # 匹配到则阻塞后续同优先级Matcher
)
# 2. 处理私聊消息 (优先级与@机器人相同)
handler_private = on_message(
    rule=Rule(
        lambda event: isinstance(event, PrivateMessageEvent)
        and is_private_available(event.user_id)  # 检查私聊AI是否启用
    ),
    permission=PRIVATE_FRIEND,
    priority=10,
    block=True,  # 私聊消息直接由本插件处理
)
# 3. 处理主动回复的上下文追问 (优先级高于初次主动判断)
active_reply_context_handler = on_message(
    rule=active_reply_context_rule,
    permission=GROUP,
    priority=15,
    block=True,  # 如果识别为追问，则应由本插件AI处理，阻塞其他
)
# 4. 处理主动回复的初次判断 (优先级较低)
active_reply_handler = on_message(
    rule=active_reply_trigger_rule,
    permission=GROUP,
    priority=20,
    block=False,  # 如果AI判断不回复，消息应可被其他插件处理
)


# --- 通用聊天处理函数 ---
async def common_chat_handler(
    bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State
):
    """所有聊天场景（@机器人、私聊、主动回复判断、主动回复追问）的统一处理入口。"""
    id_key = (
        str(event.user_id)
        if isinstance(event, PrivateMessageEvent)
        else str(event.group_id)
    )  # 会话ID (用户ID或群ID)
    chat_type = (
        "private" if isinstance(event, PrivateMessageEvent) else "group"
    )  # 会话类型

    # 从 state 中获取当前处理场景的标记
    is_active_check = state.get(
        "is_active_reply_check", False
    )  # 是否为主动回复的初次判断
    is_active_context_follow_up = state.get(
        "is_active_reply_context", False
    )  # 是否为主动回复的上下文追问

    # 忽略特定QQ号（如Q群管家）的消息，避免机器人互聊或响应管理操作
    if isinstance(event, GroupMessageEvent) and str(event.user_id) in [
        "2854196310"
    ]:  # 可配置化黑名单
        if is_active_check:
            raise IgnoredException(
                "主动回复：忽略Q群管家"
            )  # 初判时忽略，允许其他插件处理
        return  # 其他场景直接返回

    # CD检查：主动回复的初次判断不计CD；实际回复（包括追问）会计入CD
    if not check_cd(id_key) and not is_active_check:
        # logger.debug(f"用户 {event.user_id} 在 {id_key} 操作过于频繁，CD中。") # 精简日志
        # 仅在用户明确与机器人交互时（如@、私聊、或机器人已主动回复的追问）提示CD
        if (
            (isinstance(event, GroupMessageEvent) and event.to_me)
            or isinstance(event, PrivateMessageEvent)
            or is_active_context_follow_up
        ):
            await bot.send(event, "你的操作太频繁了哦！请稍后再试！", at_sender=True)
        return

    # 初始化用户/群聊的运行时配置 (如果尚不存在)
    if chat_type not in user_config:
        user_config[chat_type] = {}
    if id_key not in user_config[chat_type]:
        user_config[chat_type][id_key] = {}

    # 检查是否已选择模型
    if "model" not in user_config[chat_type][id_key]:
        if (
            is_active_check or is_active_context_follow_up
        ):  # 主动回复场景下，若无模型则静默失败
            logger.info(f"主动回复 ({chat_type} {id_key}): 未选择模型，已忽略。")
            if is_active_check:
                raise IgnoredException("主动回复：模型未选")
            return
        await bot.send(
            event,
            "你还没有选择AI模型哦，请先使用 /选择模型 <模型名> 来选择一个模型吧！",
            at_sender=True,
        )
        return

    # 队列检查：防止同一会话并发处理消息 (主动回复的初次判断不入队)
    if id_key in sequence[chat_type] and not is_active_check:
        await bot.send(event, "不要着急哦！我还在思考上一条消息呢...", at_sender=True)
        return

    images_base64 = []  # 存储消息中图片的base64编码
    # 获取选定模型的配置信息
    selected_model_config = next(
        (m for m in api_list if m.name == user_config[chat_type][id_key]["model"]), None
    )

    if (
        not selected_model_config
    ):  # 如果找不到模型配置 (理论上不应发生，因为选择模型时已校验)
        logger.error(
            f"严重错误：无法找到模型 {user_config[chat_type][id_key]['model']} 的配置信息。"
        )
        if is_active_check or is_active_context_follow_up:
            if is_active_check:
                raise IgnoredException("主动回复：模型配置丢失")
            return
        await bot.send(
            event,
            "哎呀，选中的模型配置好像不见了，请联系管理员检查下。",
            at_sender=True,
        )
        return

    # 从模型配置中提取API参数
    api_key_val = selected_model_config.api_key
    api_url_val = selected_model_config.api_url
    model_name_val = selected_model_config.model_name
    send_thinking_enabled = selected_model_config.send_thinking
    if selected_model_config.image_input:  # 如果模型支持图片输入
        images_base64 = await get_images(event, bot)  # 提取图片

    # --- 构建 System Prompt ---
    # 表情包列表字符串，供AI参考
    memes_msg_list_str = f"url - 描述"
    for meme_item in memes:
        memes_msg_list_str += f"\n            {meme_item['url']} - {meme_item['desc']}"

    # 加载角色设定/提示词 (优先级: 群专属 > 全局文件 > 配置项默认值)
    character_prompt_content = None
    if chat_type == "group":  # 仅群聊可配置群专属提示词
        group_prompt_file_path = GROUP_PROMPTS_ABSOLUTE_DIR / f"{id_key}.txt"
        if group_prompt_file_path.exists() and group_prompt_file_path.is_file():
            try:
                character_prompt_content = group_prompt_file_path.read_text(
                    encoding="utf-8"
                ).strip()
                if character_prompt_content:
                    logger.info(
                        f"群聊 {id_key} 加载专属提示词: {group_prompt_file_path.name}"
                    )  # 精简日志
                else:
                    logger.warning(
                        f"群聊 {id_key} 专属提示词文件为空: {group_prompt_file_path.name}"
                    )
                    character_prompt_content = None
            except Exception as e:
                logger.error(f"读取群聊 {id_key} 专属提示词文件失败: {e}")
                character_prompt_content = None
        # else: logger.debug(f"群聊 {id_key} 未找到专属提示词文件。") # 精简日志

    if (
        character_prompt_content is None and default_prompt_file
    ):  # 如果无群专属，尝试加载全局提示词文件
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
                        f"加载全局默认提示词文件: {default_prompt_file_path.name}"
                    )  # 精简日志
                else:
                    logger.warning(
                        f"全局默认提示词文件为空: {default_prompt_file_path.name}"
                    )
                    character_prompt_content = None
            except Exception as e:
                logger.error(f"读取全局默认提示词文件失败: {e}")
                character_prompt_content = None
        else:
            logger.warning(
                f"配置的全局默认提示词文件未找到: {default_prompt_file_path}"
            )

    if (
        character_prompt_content is None
    ):  # 如果文件加载均失败/未配置，使用配置中的默认字符串
        character_prompt_content = default_prompt
        # logger.info(f"使用配置中的默认提示词。") # 精简日志
    if not character_prompt_content:  # 最终保底，如果提示词内容仍为空
        character_prompt_content = "你是一个乐于助人的AI助手。"
        logger.warning("所有提示词来源均为空或加载失败，使用最基础的默认提示词。")

    bot_nicknames = (
        list(driver.config.nickname) if driver.config.nickname else [str(bot.self_id)]
    )  # 获取机器人昵称

    # --- 根据不同场景（主动回复判断、追问、正常对话）构建特定的AI指令 ---
    active_reply_instructions = ""
    if is_active_check:  # 初次主动回复判断
        active_reply_instructions = f"""
你正在进行一次“主动回复”判断。下面的用户消息是群聊中的一条普通消息。
你需要判断是否应该主动回复这条消息。
如果认为需要回复（例如，消息中包含明显的疑问、求助，或者是一个适合AI加入讨论的话题），请在返回的JSON中设置 "should_reply": true，并在 "messages" 字段中提供你的回复内容。
如果认为不需要回复（例如，无关紧要的闲聊、用户间的对话、机器人不宜介入的内容），请设置 "should_reply": false，此时 "messages" 字段可以为空或包含你的内部思考（此思考内容不会被发送）。
请优先回复那些看起来确实需要你帮助或参与的消息。"""
    elif is_active_context_follow_up:  # 主动回复后的追问判断
        active_reply_instructions = f"""
你之前在这个群聊中主动回复了一条消息。现在收到了后续的用户消息。
你需要仔细判断这条新的用户消息是否是针对你先前主动回复的直接追问、提问或延续讨论。
- 如果是直接的追问或相关讨论，请正常回复，并在 "messages" 字段提供回复内容。同时设置 "should_reply": true。
- 如果新的用户消息看起来与你之前的回复无关（例如：用户开始了一个全新的话题，或者明显是在和其他群成员对话，或者是一条不适宜回复的普通消息），那么你应该明确指示不回复。要做到这一点，请确保返回的JSON中 "should_reply": false，并且 "messages" 字段为一个空列表 `[]`。

例如，如果用户问：“机器人你叫什么名字？”，这是对你的直接提问，你应该回复。
如果用户说：“今天天气真好啊！@张三 我们去打球吧”，这很可能不是对你的追问，你应该指示不回复。
"""

    # 完整的 System Prompt 文本
    system_prompt_text = f"""
我需要你在群聊中进行闲聊。大家通常会称呼你为{"、".join(bot_nicknames)}。我会在后续信息中告诉你每条群聊消息的发送者和发送时间，你可以直接称呼发送者为他们的昵称。
{active_reply_instructions}
你的回复需要遵守以下规则：
- 不要使用 Markdown 或 HTML 格式。聊天软件不支持解析，换行请用换行符。
- 以普通人的口吻发送消息，每条消息适当简短，但对于某些说明解释性的回复以及你认为需要适中篇幅介绍的回答，考虑使用较长的消息。
- 纯文本消息可以分多条回复，但请控制在 {max_split_length} 条消息以内。戳一戳,表情包和禁言等特殊消息不受限制。
- 如果需要发送代码，请用单独的一条消息发送，不要分段。
- 使用发送者的昵称称呼对方。第一次回复时可以礼貌问候，但后续无需重复问候。
- 如果需要思考，直接用普通文本表达，不要用 JSON 格式。
- 不要在思考内容中提到 JSON 或其他格式要求。

以下是你的性格设定，如果设定中提到让你扮演某个人或有名字，则优先使用设定中的名字;如果设定中要求了消息的文本长度，则使用设定中的文本长度要求：
{character_prompt_content}
重要!!!你的正文回复必须统一使用 JSON 格式，所有回复内容将包裹在一个字典里。字典中的 `messages` 字段代表你的回复，你还可以根据情景向字典里添加其他参数。可用的参数如下：
- `reply`：布尔值，是否回复用户的消息。如果是回复，请在 `msg_id` 字段内填入消息 ID。注意:私聊消息请不要回复。{"对于主动回复判断的场景，此字段通常应为 false，因为不是对用户某条消息的直接“引用回复”。" if is_active_check else ""}
{"- `should_reply`：布尔值，仅用于主动回复判断场景，指示机器人是否应该回复这条消息。在追问场景，如果AI判断不应回复，也应设为false或返回空messages。" if is_active_check or is_active_context_follow_up else ""}
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
- 严禁说明回复的是 JSON 格式，必须直接输出 JSON 字符串。

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
    {', "should_reply": true' if is_active_check or is_active_context_follow_up else ''} 
}}
```"""

    # --- 初始化或更新聊天记录中的System Prompt ---
    current_messages_history = []  # 当前会话的完整历史记录 (包括system prompt)
    if (
        "messages" not in user_config[chat_type][id_key]
        or not user_config[chat_type][id_key]["messages"]
    ):
        current_messages_history = [{"role": "system", "content": system_prompt_text}]
    else:
        current_messages_history = user_config[chat_type][id_key]["messages"]
        if current_messages_history and current_messages_history[0]["role"] == "system":
            current_messages_history[0][
                "content"
            ] = system_prompt_text  # 更新已存在的system prompt
        else:
            current_messages_history.insert(
                0, {"role": "system", "content": system_prompt_text}
            )  # 添加新的system prompt
    user_config[chat_type][id_key][
        "messages"
    ] = current_messages_history  # 将更新后的历史存回

    # --- 处理引用回复信息 (仅在非主动回复场景) ---
    replied_text_info = ""
    if event.reply and not is_active_check and not is_active_context_follow_up:
        original_message_id_to_log = "N/A"
        try:
            if hasattr(event.reply, "message_id"):
                original_message_id_to_log = event.reply.message_id
            else:
                raise AttributeError("event.reply 对象没有属性 'message_id'")
            msg_id_val = event.reply.message_id
            if isinstance(msg_id_val, str):
                cleaned_id_str = msg_id_val.strip()
                original_message_id = int(cleaned_id_str)
            elif isinstance(msg_id_val, int):
                original_message_id = msg_id_val
            else:
                raise TypeError(f"event.reply.message_id 类型错误: {type(msg_id_val)}")

            original_msg_data = await bot.get_msg(message_id=original_message_id)
            if original_msg_data and "message" in original_msg_data:
                raw_message_content = original_msg_data["message"]
                processed_segments = []
                if isinstance(raw_message_content, str):
                    temp_msg_obj = OneBotMessage(raw_message_content)
                    processed_segments.extend(seg for seg in temp_msg_obj)
                elif isinstance(raw_message_content, list):
                    for seg_dict in raw_message_content:
                        if (
                            isinstance(seg_dict, dict)
                            and "type" in seg_dict
                            and "data" in seg_dict
                        ):
                            try:
                                processed_segments.append(
                                    MessageSegment(
                                        type=seg_dict["type"], data=seg_dict["data"]
                                    )
                                )
                            except Exception as e_seg_create:
                                logger.warning(
                                    f"AITalk Warning: 从字典 {seg_dict} 创建 MessageSegment 失败: {e_seg_create}."
                                )
                                processed_segments.append(
                                    MessageSegment.text(str(seg_dict))
                                )
                        else:
                            logger.warning(
                                f"AITalk Warning: 消息列表中的项目不是有效的消息段字典: {str(seg_dict)[:100]}."
                            )
                            processed_segments.append(
                                MessageSegment.text(str(seg_dict))
                            )
                elif isinstance(raw_message_content, dict):
                    if "type" in raw_message_content and "data" in raw_message_content:
                        try:
                            processed_segments.append(
                                MessageSegment(
                                    type=raw_message_content["type"],
                                    data=raw_message_content["data"],
                                )
                            )
                        except Exception as e_seg_create:
                            logger.warning(
                                f"AITalk Warning: 从单个字典 {raw_message_content} 创建 MessageSegment 失败: {e_seg_create}."
                            )
                            processed_segments.append(
                                MessageSegment.text(str(raw_message_content))
                            )
                    else:
                        logger.warning(
                            f"AITalk Warning: 单个消息字典不是有效的消息段字典: {str(raw_message_content)[:100]}."
                        )
                        processed_segments.append(
                            MessageSegment.text(str(raw_message_content))
                        )
                else:
                    logger.error(
                        f"AITalk Error: 来自 bot.get_msg 的消息格式未预期: {type(raw_message_content)}."
                    )
                    processed_segments.append(
                        MessageSegment.text(str(raw_message_content))
                    )
                original_message_obj = OneBotMessage(processed_segments)
                original_text = original_message_obj.extract_plain_text().strip()
                original_sender_nickname = original_msg_data.get("sender", {}).get(
                    "nickname", "未知用户"
                )
                if original_text:
                    replied_text_info = f"""- 用户回复了【{original_sender_nickname}】的消息: "{original_text}"\n    """
            # else: logger.debug(f"bot.get_msg 未返回有效消息内容。ID: {original_message_id}") # 精简日志
        except (ValueError, TypeError, AttributeError) as e_parse:
            logger.warning(
                f"处理被回复消息时发生解析错误。ID: '{original_message_id_to_log}'. 错误: {e_parse}",
                exc_info=False,
            )  # 精简日志
        except Exception as e:
            logger.warning(
                f"获取或解析被回复消息文本时发生未知错误。ID: '{original_message_id_to_log}'. 错误: {e}",
                exc_info=False,
            )  # 精简日志

    # --- 构建用户向AI提问的文本 ---
    user_plain_text = event.get_plaintext()
    user_prompt_content_for_ai = f"用户说：{user_plain_text}"  # 默认情况
    if not user_plain_text and images_base64:  # 如果没有文本但有图片
        user_prompt_content_for_ai = (
            "用户发送了一张或多张图片，请理解图片内容并作回应。"
        )
    elif user_plain_text and images_base64:  # 如果既有文本又有图片
        user_prompt_content_for_ai = f"用户发送了图片并说：{user_plain_text}"

    user_prompt_prefix = ""  # 根据场景调整前缀
    if is_active_check:
        user_prompt_prefix = (
            "这是一条普通群聊消息，请你判断是否需要主动回复，并给出回复内容：\n"
        )
    elif is_active_context_follow_up:
        user_prompt_prefix = (
            "这是在你主动回复后的用户消息，请判断是否为追问并酌情回复：\n"
        )

    # 最终的用户提示文本
    user_prompt_text = f"""{user_prompt_prefix}
    - 用户昵称：{event.sender.nickname}
    - 用户QQ号: {event.user_id}
    - 消息时间：{time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(event.time))}
    - 消息id: {str(event.message_id)}
    - 群号: {str(event.group_id) if isinstance(event,GroupMessageEvent) else "这是一条私聊消息"}
    {replied_text_info} 
    - {user_prompt_content_for_ai} 
    """

    # --- 构建发送给AI的最终消息列表 ---
    # 对于初次主动回复判断，API的上下文只包含system prompt和当前用户消息
    if is_active_check:
        messages_to_send_to_api = [
            user_config[chat_type][id_key]["messages"][0],  # System prompt
        ]
    else:  # 正常对话或主动回复的追问，使用截断后的历史记录
        messages_to_send_to_api = user_config[chat_type][id_key]["messages"][
            :
        ]  # 创建副本进行操作
        # 确保上下文长度，但system prompt必须保留
        if (
            len(messages_to_send_to_api) >= max_context_length
        ):  # 注意这里用的是 messages_to_send_to_api 的长度
            system_message = messages_to_send_to_api[0]
            recent_messages = messages_to_send_to_api[-(max_context_length - 2) :]
            messages_to_send_to_api = [system_message] + recent_messages
            # 注意：这里不应修改 user_config 中的历史，截断应只针对本次API调用
            # 历史记录的持久化截断应在成功收到AI回复并添加到历史之后进行（如果需要）
            # 但当前代码是在添加新消息前就截断 user_config，所以这里保持一致

    # 将当前用户消息加入到待发送列表
    user_message_content_list = [{"type": "text", "text": user_prompt_text}]
    if images_base64:
        for img_b64 in images_base64:
            user_message_content_list.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                }
            )
    current_user_message_for_api = {
        "role": "user",
        "content": user_message_content_list,
    }
    messages_to_send_to_api.append(current_user_message_for_api)

    try:
        # 主动回复的初次判断不入处理队列
        if not is_active_check:
            sequence[chat_type].append(id_key)

        # 调用AI生成回复
        reply_content_str, thinking_content_str, success, err_msg = await gen(
            messages_to_send_to_api,
            model_name_val,
            api_key_val,
            api_url_val,
        )

        if not success:  # AI生成失败
            if is_active_check:  # 初判失败，静默处理并允许其他插件
                logger.error(
                    f"主动回复判断：AI生成失败 ({chat_type} {id_key}): {err_msg}"
                )
                raise IgnoredException(f"主动回复判断：AI生成失败: {err_msg}")
            # 其他场景，向用户发送错误提示
            await bot.send(
                event, err_msg if err_msg else "AI生成回复失败了...", at_sender=True
            )
            # 注意：此处不从 user_config 中 pop 消息，因为用户消息还未正式加入历史
            return

        # logger.debug(f"AI原始回复 ({chat_type} {id_key}{' - 主动判断' if is_active_check else (' - 主动追问' if is_active_context_follow_up else '')}): {str(reply_content_str)[:100]}...") # 精简日志

        if reply_content_str is None:  # AI未返回任何内容
            if is_active_check:
                logger.warning(
                    f"主动回复判断：AI未能生成回复内容 (返回None) ({chat_type} {id_key})"
                )
                raise IgnoredException("主动回复判断：AI返回None")
            await bot.send(event, "AI好像有点累了，什么都没说...", at_sender=True)
            return

        # --- 根据不同场景处理AI回复 ---
        if is_active_check:  # 场景：主动回复的初次判断
            # 解析AI的判断结果和回复内容，并尝试修复JSON（如果需要）
            should_really_reply, formatted_reply_list = await format_reply(
                reply_content_str,
                for_active_check=True,
                model_config_for_repair=selected_model_config,
            )

            if should_really_reply and formatted_reply_list:  # AI判断需要回复且有内容
                logger.info(
                    f"主动回复：AI判断需要回复群聊 {id_key} 的消息 (ID: {event.message_id})。"
                )
                await send_formatted_reply(
                    bot, event, formatted_reply_list, should_reply=False
                )  # 主动回复不引用原消息
                add_cd(id_key)  # 添加CD

                # 创建主动回复会话记录
                active_reply_sessions[id_key] = {
                    "last_bot_reply_time": time.time(),
                    "original_user_msg_id": str(event.message_id),
                    "last_interaction_time": time.time(),
                    "unrelated_followup_count": 0,
                }
                # 将此轮成功的交互（用户的原始消息 + AI的回复）加入到该会话的聊天历史中
                # 注意：current_user_message_for_api 包含的是包装后的用户提示，不是原始event
                # 为了上下文的连贯性，这里保存的是包装后的用户提示和AI的原始JSON回复
                user_config[chat_type][id_key]["messages"].append(
                    current_user_message_for_api
                )  # 将用于判断的用户消息加入历史
                user_config[chat_type][id_key]["messages"].append(
                    {"role": "assistant", "content": reply_content_str}
                )  # AI的回复也加入历史
            else:  # AI判断不需要回复或回复内容为空
                logger.info(
                    f"主动回复：AI判断不需要回复群聊 {id_key} 的消息 (ID: {event.message_id})。"
                )
                # 此处抛出 IgnoredException 是为了让 NoneBot 知道这个 handler 不再处理，
                # 并且由于 active_reply_handler 的 block=False，其他插件仍有机会处理。
                # NoneBot 日志中可能会出现 ERROR 记录此 IgnoredException (如果无其他插件处理)，这是预期行为。
                raise IgnoredException("主动回复：AI判断不回复或内容为空")
            return  # 主动回复初次判断流程结束

        # --- 场景：正常对话 或 主动回复的上下文追问 ---
        # 1. 将用户的提问加入到永久历史记录中
        user_config[chat_type][id_key]["messages"].append(current_user_message_for_api)
        # 2. 将AI的回复也加入到永久历史记录中
        user_config[chat_type][id_key]["messages"].append(
            {"role": "assistant", "content": reply_content_str}
        )

        # （可选）发送思考中消息
        if send_thinking_enabled and thinking_content_str:
            await send_thinking_msg(bot, event, thinking_content_str, bot_nicknames)

        # 解析AI回复用于发送给用户 (如果需要，也进行JSON修复)
        # 对于追问场景，for_active_check应为True，以便能解析should_reply来判断是否真为追问
        parsed_result_tuple_or_list = await format_reply(
            reply_content_str,
            for_active_check=is_active_context_follow_up,
            model_config_for_repair=selected_model_config,
        )

        actual_parsed_list_to_send = []  # 最终要发送给用户的消息列表
        is_related_followup_by_ai = True  # AI是否认为这是相关追问 (仅在追问场景下有效)

        if is_active_context_follow_up:  # 如果是追问场景
            if (
                isinstance(parsed_result_tuple_or_list, tuple)
                and len(parsed_result_tuple_or_list) == 2
            ):
                is_related_followup_by_ai, actual_parsed_list_to_send = (
                    parsed_result_tuple_or_list
                )
                if not is_related_followup_by_ai:  # AI判断不是相关追问
                    logger.info(
                        f"主动回复追问场景：AI明确指示不回复 (should_reply=false)。群聊 {id_key}, 用户 {event.user_id}."
                    )
            else:  # format_reply 未返回预期的元组
                logger.error(
                    f"内部错误：format_reply 在追问场景未返回 (bool, list) 元组。实际返回: {type(parsed_result_tuple_or_list)}"
                )
                actual_parsed_list_to_send = []  # 安全起见，视为空列表
                is_related_followup_by_ai = False  # 视为不相关
        else:  # 正常对话场景
            actual_parsed_list_to_send = (
                parsed_result_tuple_or_list
                if isinstance(parsed_result_tuple_or_list, list)
                else []
            )

        # 如果最终没有可发送的消息内容 (例如AI在追问时判断不相关且返回空messages)
        if not actual_parsed_list_to_send:
            if is_active_context_follow_up:  # 仅在追问场景下处理“无内容回复”
                logger.info(
                    f"主动回复追问场景：AI判断无需回复或返回空内容。群聊 {id_key}, 用户 {event.user_id}."
                )
                if id_key in active_reply_sessions:
                    active_reply_sessions[id_key][
                        "last_interaction_time"
                    ] = time.time()  # 更新最后互动时间
                    # 如果AI判断不是相关追问，并且启用了最大无关追问次数限制
                    if (
                        not is_related_followup_by_ai
                        and active_reply_max_unrelated_followups > 0
                    ):
                        count = (
                            active_reply_sessions[id_key].get(
                                "unrelated_followup_count", 0
                            )
                            + 1
                        )
                        active_reply_sessions[id_key][
                            "unrelated_followup_count"
                        ] = count
                        logger.info(f"群聊 {id_key} 无关追问计数: {count}")
                        if count >= active_reply_max_unrelated_followups:
                            logger.info(
                                f"群聊 {id_key} 达到最大无关追问次数 ({active_reply_max_unrelated_followups})，关闭主动回复会话。"
                            )
                            del active_reply_sessions[id_key]  # 关闭会话
                return  # 直接返回，不发送任何消息

        # 准备发送消息
        should_reply_event_msg_flag, original_msg_id_to_reply_val = need_reply_msg(
            reply_content_str, event
        )

        if is_active_context_follow_up:  # 如果是主动回复的追问场景
            should_reply_event_msg_flag = (
                False  # 追问时不“引用回复”最初那条被主动回应的用户消息
            )
            if id_key in active_reply_sessions:
                active_reply_sessions[id_key][
                    "last_interaction_time"
                ] = time.time()  # 更新会话互动时间
                if is_related_followup_by_ai:  # 如果AI认为是相关追问，重置无关计数器
                    active_reply_sessions[id_key]["unrelated_followup_count"] = 0
                    logger.debug(f"群聊 {id_key} 追问被AI判断为相关，重置无关计数。")

        await send_formatted_reply(
            bot,
            event,
            actual_parsed_list_to_send,
            should_reply_event_msg_flag,
            original_msg_id_to_reply_val,
        )
        if not is_active_check:
            add_cd(id_key)  # 初次主动判断不计CD，其他所有成功交互（包括追问）都计CD

    except (
        IgnoredException
    ) as e:  # 捕获由本处理函数或下层调用（如format_reply中的初判）抛出的IgnoredException
        # logger.debug(f"消息处理被忽略（IgnoredException）: {e.args[0] if e.args else 'No reason provided'}") # 精简日志
        raise  # 重新抛出，由NoneBot核心处理 (对于block=False的matcher，允许其他matcher尝试)
    except Exception as e:  # 其他所有未预料的异常
        logger.error(
            f"AI处理过程中发生严重错误 ({chat_type} {id_key}): {e}", exc_info=True
        )  # 记录完整错误信息
        error_message_text = f"哎呀，AI思考的时候好像出了点大问题！请稍后再试或联系管理员。"  # 通用错误提示
        # 主动回复的初次判断如果在这里出错，也不应打扰用户
        if not is_active_check:
            await bot.send(
                event, error_message_text, at_sender=True, reply_message=True
            )
    finally:
        # 确保从处理队列中移除 (仅对非初次主动判断的交互)
        if not is_active_check and id_key in sequence[chat_type]:
            sequence[chat_type].remove(id_key)


# --- 绑定主处理函数到各个 Matcher ---
handler.handle()(common_chat_handler)
handler_private.handle()(common_chat_handler)
active_reply_handler.handle()(common_chat_handler)
active_reply_context_handler.handle()(common_chat_handler)


@driver.on_startup
async def _():
    """插件启动时执行的钩子函数，用于加载用户配置。"""
    if save_user_config:  # 如果启用了保存用户配置
        global user_config
        saved_data = read_all_data()  # 从本地存储读取数据
        if saved_data:
            for chat_type_key in ["private", "group"]:
                if chat_type_key in saved_data:
                    user_config[chat_type_key] = {}  # 初始化
                    for id_val, config_data_val in saved_data[chat_type_key].items():
                        user_config[chat_type_key][id_val] = {}
                        if "model" in config_data_val:  # 只恢复模型选择
                            user_config[chat_type_key][id_val]["model"] = (
                                config_data_val["model"]
                            )
            logger.info("用户运行时配置 (模型选择) 已从本地加载。")
        else:
            user_config = {
                "private": {},
                "group": {},
            }  # 未找到文件或文件为空，使用默认空配置
            logger.info("未找到用户运行时配置文件，使用默认空配置。")


@driver.on_shutdown
async def _():
    """插件关闭时执行的钩子函数，用于保存用户配置。"""
    if save_user_config:  # 如果启用了保存用户配置
        global user_config
        data_to_save = {"private": {}, "group": {}}
        for chat_type_key in ["private", "group"]:
            if chat_type_key in user_config:
                data_to_save[chat_type_key] = {}
                for id_val, config_data_val in user_config[chat_type_key].items():
                    data_to_save[chat_type_key][id_val] = {}
                    if "model" in config_data_val:  # 只保存模型选择
                        data_to_save[chat_type_key][id_val]["model"] = config_data_val[
                            "model"
                        ]
        write_all_data(data_to_save)
        logger.info("用户运行时配置 (模型选择) 已保存。")
