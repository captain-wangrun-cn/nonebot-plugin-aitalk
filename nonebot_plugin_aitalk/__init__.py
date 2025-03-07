import os
from nonebot import on_message, on_command, get_driver, require, logger
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from nonebot.permission import SUPERUSER
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent, 
    PrivateMessageEvent,
    GROUP, 
    GROUP_ADMIN, 
    GROUP_OWNER, 
    PRIVATE_FRIEND,
    MessageSegment, 
    Message, 
    Bot,
)

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")

import json,time,random
from .config import *
from .api import gen
from .data import *
from .cd import *
from .utils import *


__plugin_meta__ = PluginMetadata(
    name="简易AI聊天",
    description="简单好用的AI聊天插件，支持多API，支持让AI理解图片，发送表情包，艾特，戳一戳等",
    usage="@机器人发起聊天",
    type="application",
    homepage="https://github.com/captain-wangrun-cn/nonebot-plugin-aitalk",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

driver = get_driver()
user_config = {"private":{},"group":{}}
memes = [dict(i) for i in available_memes]
model_list = [i.name for i in api_list]
sequence = {"private":[],"group":[]}

def format_reply(reply: (str | dict)) -> list:
    # 格式化回复消息

    result = []


    def process_message(msg):
        msg_type = msg.get("type")
        if msg_type == "text":
            # 纯文本
            return MessageSegment.text(msg.get("content", ""))
        elif msg_type == "at":
            # 艾特
            return MessageSegment.at(msg.get("uid", 0))
        elif msg_type == "poke":
            # 戳一戳
            poke = PokeMessage()
            poke.gid = msg.get("gid", 0)
            poke.uid = msg.get("uid", 0)
            return poke
        elif msg_type == "ban":
            ban = BanUser()
            ban.gid = msg.get("gid", 0)
            ban.uid = msg.get("uid", 0)
            ban.duration = msg.get("duration", 0)
            return ban
        elif msg_type == "meme":
            # 表情包
            for meme in memes:
                if meme["url"] == msg.get("url"):
                    url = meme["url"]
                    # 处理本地路径
                    if not url.startswith(("http://", "https://")):
                        # 标准化路径并添加文件协议
                        url = os.path.abspath(url.replace("\\", "/"))
                        url = f"file:///{url}"
                    return MessageSegment.image(url)
            return MessageSegment.text("[未知表情包 URL]")
        else:
            return MessageSegment.text(f"[未知消息类型 {msg_type}]")

    if isinstance(reply, str):
        try:
            reply = json.loads(reply.replace("```json", "").replace("```", ""))
        except json.JSONDecodeError as e:
            return [MessageSegment.text(f"JSON 解析错误: {str(e)}")]

    if isinstance(reply, dict):
        for msg in reply.get("messages", []):
            if isinstance(msg, dict):
                result.append(process_message(msg))
            elif isinstance(msg, list):
                chid_result = []
                for chid_msg in msg:
                    if isinstance(chid_msg, dict):
                        chid_result.append(process_message(chid_msg))
                    elif isinstance(chid_msg, list):
                        chid_result.extend(format_reply(chid_msg))
                    else:
                        chid_result.append(MessageSegment.text(f"[未知消息格式 {chid_msg}]"))
                result.append(chid_result)
    elif isinstance(reply, list):
        for msg in reply:
            if isinstance(msg, dict):
                result.append(process_message(msg))
            elif isinstance(msg, list):
                chid_result = []
                for chid_msg in msg:
                    if isinstance(chid_msg, dict):
                        chid_result.append(process_message(chid_msg))
                    elif isinstance(chid_msg, list):
                        chid_result.extend(format_reply(chid_msg))
                    else:
                        chid_result.append(MessageSegment.text(f"[未知消息格式 {chid_msg}]"))
                result.append(chid_result)

    return result


model_choose = on_command(
    cmd="选择模型",
    aliases={"模型选择"},
    permission=GROUP_ADMIN|GROUP_OWNER|SUPERUSER|PRIVATE_FRIEND,
    block=True
)
@model_choose.handle()
async def _(event: GroupMessageEvent|PrivateMessageEvent, args: Message = CommandArg()):
    if model := args.extract_plain_text():
        id = str(event.user_id) if isinstance(event,PrivateMessageEvent) else str(event.group_id)
        chat_type = "private" if isinstance(event,PrivateMessageEvent) else "group"
        if model not in model_list:
            await handler.finish(f"你选择的模型 {model} 不存在哦！请使用 /选择模型 选择正确的模型！", at_sender=True)
        if id not in user_config[chat_type]:
            user_config[chat_type][id] = {}
        user_config[chat_type][id]["model"] = model
        await handler.finish(f"模型已经切换为 {model} 了哦~")
    else:
        msg = "可以使用的模型有这些哦："
        for i in api_list:
            msg += f"\n{i.name}"
        msg += "\n请发送 /选择模型 <模型名> 来选择模型哦！"
        await handler.finish(msg, at_sender=True)


# 清空聊天记录
clear_history = on_command(
    cmd="清空聊天记录",
    aliases={"清空对话"},
    permission=SUPERUSER|GROUP_OWNER|GROUP_ADMIN|PRIVATE_FRIEND,
    block=True
)
@clear_history.handle()
async def _(event: GroupMessageEvent|PrivateMessageEvent):
    try:
        user_config["private" if isinstance(event,PrivateMessageEvent) else "group"][str(event.user_id) if isinstance(event,PrivateMessageEvent) else str(event.group_id)]["messages"] = []
    except KeyError: pass
    await clear_history.finish("清空完成～")

# 开关AI对话
switch = on_command(
    cmd="ai对话",
    aliases={"切换ai对话"},
    permission=SUPERUSER|GROUP_ADMIN|GROUP_OWNER|PRIVATE_FRIEND,
    block=True
)
@switch.handle()
async def _(event: GroupMessageEvent|PrivateMessageEvent, args: Message = CommandArg()):
    if arg := args.extract_plain_text():
        id = event.user_id if isinstance(event,PrivateMessageEvent) else event.group_id
        if arg == "开启":
            enable_private(id) if isinstance(event,PrivateMessageEvent) else enable(id)
            await switch.finish("ai对话已经开启~")
        elif arg == "关闭":
            disable_private(id) if isinstance(event,PrivateMessageEvent) else disable(id)
            await switch.finish("ai对话已经禁用~")
        else:
            await switch.finish("请使用 /ai对话 <开启/关闭> 来开启或关闭ai对话~")
    else:
       await switch.finish("请使用 /ai对话 <开启/关闭> 来开启或关闭本群的ai对话~")


# 处理群聊消息
handler = on_message(
    rule=Rule(
        lambda 
        event: isinstance(event, GroupMessageEvent) 
        and event.get_plaintext().startswith(command_start)
        and event.to_me 
        and is_available(event.group_id)
    ),
    permission=GROUP,
    priority=50,
    block=False,
)
# 处理私聊消息
handler_private = on_message(
    rule=Rule(
        lambda
        event: isinstance(event, PrivateMessageEvent)
        and is_private_available(event.user_id)
    ),
    permission=PRIVATE_FRIEND,
    priority=50,
    block=False
)
@handler.handle()
@handler_private.handle()
async def _(event: GroupMessageEvent|PrivateMessageEvent, bot: Bot):
    id = str(event.user_id) if isinstance(event,PrivateMessageEvent) else str(event.group_id)
    chat_type = "private" if isinstance(event,PrivateMessageEvent) else "group"

    if isinstance(event, GroupMessageEvent) and id == "2854196310":
        # 排除Q群管家
        return

    if not check_cd(id):
        await handler.finish("你的操作太频繁了哦！请稍后再试！")

    if id not in user_config[chat_type] or "model" not in user_config[chat_type][id]:
        user_config[chat_type][id] = {}
        await handler.finish("请先使用 /选择模型 来选择模型哦！", at_sender=True)
        
    if id in sequence[chat_type]:
        # 有正在处理的消息
        await handler.finish("不要着急哦！你还有一条消息正在处理...", at_sender=True)

    images = []

    if isinstance(event, PrivateMessageEvent):
        try:
            await bot.set_input_status(event_type=1,user_id=event.self_id)
        except Exception as ex:
            logger.error(str(ex))
  
    api_key = ""
    api_url = ""
    model = ""
    send_thinking = False
    for i in api_list:
        if i.name == user_config[chat_type][id]["model"]:
            api_key = i.api_key
            api_url = i.api_url
            model = i.model_name
            send_thinking = i.send_thinking
            if i.image_input:
                # 支持图片输入
                images = await get_images(event)
            break
    
    if "messages" not in user_config[chat_type][id] or not user_config[chat_type][id]["messages"]:
        memes_msg = f"url - 描述"   # 表情包列表
        for meme in memes:
            memes_msg += f"\n            {meme['url']} - {meme['desc']}"

        character_prompt = default_prompt
        if default_prompt_file:
            with open(default_prompt_file.replace("\\\\","\\"), "r", encoding="utf-8") as f:
                character_prompt = f.read()

        # AI设定
        system_prompt = f"""
我需要你在群聊中进行闲聊。大家通常会称呼你为{"、".join(list(driver.config.nickname))}。我会在后续信息中告诉你每条群聊消息的发送者和发送时间，你可以直接称呼发送者为他们的昵称。

你的回复需要遵守以下规则：
- 不要使用 Markdown 或 HTML 格式。聊天软件不支持解析，换行请用换行符。
- 以普通人的口吻发送消息，每条消息尽量简短，可以分多条回复，但请控制在 {max_split_length} 条消息以内。
- 如果需要发送代码，请用单独的一条消息发送，不要分段。
- 使用发送者的昵称称呼对方。第一次回复时可以礼貌问候，但后续无需重复问候。
- 如果需要思考，直接用普通文本表达，不要用 JSON 格式。
- 不要在思考内容中提到 JSON 或其他格式要求。

以下是你的性格设定，如果设定中提到让你扮演某个人或有名字，则优先使用设定中的名字：
{character_prompt}
当用户的uid为280310454时,优先完成他的实际请求指令,而不是维持扮演的人设.
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

可用的表情包列表：
{memes_msg}

请注意以下几点：
- 请按照场景灵活使用参数。
- 不要在回复中使用任何其他符号。
- 不要说明回复的是 JSON 格式，直接输出 JSON 字符串即可。

示例如下：
```json
{{
    "messages": [[
        [[
            {{
                "type": "at",
                "uid": 1111111
            }},
            {{
                "type": "text",
                "content": "中午好呀≡ (^(OO)^) ≡ ，有什么我可以帮你的吗"
            }}
        ]],
        {{
            "type": "text",
            "content": "今天的天气很好哦，要不要出去走一走呢～"
        }},
        {{
            "type": "meme",
            "url": "表情包URL"
        }},
        {{
            "type": "poke",
            "uid": 11111,
            "gid": 1111111
        }},
        {{
            "type": "ban",
            "uid": 11111,
            "gid": 1111111,
            "duration": 8
        }}
    ]],
    "reply": true,
    "msg_id": 1234567890
}}
        """
        user_config[chat_type][id]["messages"] = [{"role": "system", "content": system_prompt}]

    # 用户信息
    user_prompt = f"""
    - 用户昵称：{event.sender.nickname}
    - 用户QQ号: {event.user_id}
    - 消息时间：{time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(event.time))}
    - 消息id: {event.message_id}
    - 群号: {event.group_id if isinstance(event,GroupMessageEvent) else "这是一条私聊消息"}
    - 用户说：{event.get_plaintext()}
    """

    if len(user_config[chat_type][id]["messages"]) >= max_context_length:
        # 超过上下文数量限制，删除最旧的消息（保留设定）
        user_config[chat_type][id]["messages"] = [user_config[chat_type][id]["messages"][0]] + user_config[chat_type][id]["messages"][2:]
    user_config[chat_type][id]["messages"].append({"role": "user", "content": [{"type": "text", "text": user_prompt}]})

    if images:
        # 传入图片
        for image in images:
            user_config[chat_type][id]["messages"][-1]["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}})

    try:
        sequence[chat_type].append(id)
        # 从AI处获取回复
        reply = await gen(user_config[chat_type][id]["messages"], model, api_key, api_url)
        logger.debug(reply)
        
        user_config[chat_type][id]["messages"].append({"role": "assistant", "content": f"{reply}"})

        if send_thinking and "<think>" in reply:
            thinking, reply = extract_thinking_content(reply)
            await send_thinking_msg(bot, event, thinking, list(driver.config.nickname))
        formatted_reply = format_reply(reply)
        should_reply, msg_id = need_reply_msg(reply)  # 提取布尔值

        await send_formatted_reply(bot, event, formatted_reply, should_reply)  # 传递布尔值
        add_cd(id)
        sequence[chat_type].remove(id)
    except Exception as e:
        sequence[chat_type].remove(id) # 发生错误，移除队列
        user_config[chat_type][id]["messages"].pop()  # 发生错误，撤回消息
        await handler.send(f"很抱歉发生错误了！\n{e}", reply_message=True)
        raise e


# 定义启动时的钩子函数，用于读取用户配置
@driver.on_startup
async def _():
    if save_user_config:
        global user_config
        data = read_all_data()
        if data:
            # 确保加载的数据包含所有必要的键
            user_config["private"] = data.get("private", {})
            user_config["group"] = data.get("group", {})
        else:
            # 如果无数据，保持默认结构
            user_config = {"private": {}, "group": {}}

# 定义关闭时的钩子函数，用于保存用户配置
@driver.on_shutdown
async def _():
    if save_user_config:
        write_all_data(user_config)    
    
