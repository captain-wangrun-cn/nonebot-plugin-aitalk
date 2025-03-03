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

import json,time
from .config import *
from .api import gen
from .data import *
from .cd import *
from .utils import *

__plugin_meta__ = PluginMetadata(
    name="简易AI聊天",
    description="简单好用的AI聊天插件，支持多API，支持发送表情包，艾特，戳一戳等",
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
        elif msg_type == "meme":
            # 表情包
            for meme in memes:
                if meme["url"] == msg.get("url"):
                    url = meme["url"]
                    if not url.startswith("http://") and not url.startswith("https://"):
                        url = url.replace("/","\\\\")
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
            disable_private(id) if isinstance(event,PrivateMessagEvent) else disable(id)
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
    for i in api_list:
        if i.name == user_config[chat_type][id]["model"]:
            api_key = i.api_key
            api_url = i.api_url
            model = i.model_name
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
        我想要你帮我在群聊中闲聊，大家一般叫你{"、".join(list(driver.config.nickname))}，我将会在后面的信息中告诉你每条群聊信息的发送者和发送时间，你可以直接称呼发送者为他对应的昵称。
        你的回复需要遵守以下几点规则：
        - 不要使用markdown或者html，聊天软件不支持解析，换行请用换行符。
        - 你应该以普通人的方式发送消息，每条消息字数要尽量少一些，适当倾向于使用更多条的消息回复。但是，请务必你控制在{max_split_length}条消息内！！
        - 代码则不需要分段，用单独的一条消息发送。
        - 请使用发送者的昵称称呼发送者，你可以礼貌地问候发送者，但只需要在第一次回答这位发送者的问题时问候他。
        - 如果你需要思考的话，你应该思考尽量少，以节省时间。
        下面是关于你性格的设定，如果设定中提到让你扮演某个人，或者设定中有提到名字，则优先使用设定中的名字。
        {character_prompt}
        并且，请将你的回复统一使用json格式
        所有的回复将会包裹在一个字典里

        字典中的messages字段代表你的回复，你还可以根据情景向字典里添加其他参数
        可用的参数有:
            reply - 布尔值 - 是否回复用户的消息，如回复，则在msg_id字段内填入消息id。注意，私聊消息请不要回复！
            messages字段是一个列表，你向里面可以添加字典或列表，如果是列表，则代表列表中的所有内容为一句话；如果为字典，则是一句话。
            请用一个字典代表一句话。
            其中，type字段代表类型，可用的值有:
                at - 艾特某人 - 需要在uid字段中填入要艾特的用户id，艾特发送者是非必要的，你可以根据你自己的想法艾特某个人。
                text - 纯文本消息 - 需要在content字段中填入内容
                poke - 发送戳一戳 - 需要在uid字段中填入用户id，gid字段中填入群号
                meme - 图片表情包 - 需要在url字段中填入表情包的url，我在后面将会把所有的表情包告诉你

        可用的表情包列表:
            {memes_msg}

        最后，你只需要参考格式，而不需要参考性格和内容。请按照场景，在合适的时间使用参数。
        不要在回复中使用任何其他符号，不要说明回复的是json语言，请直接回复json字符串数据
        
        示例如下：
        {{
            "messages": [
                [
                    {{
                        "type": "at",
                        "uid": 1111111
                    }},
                    {{
                        "type": "text",
                        "content": "中午好呀≡ (^(OO)^) ≡ ，有什么我可以帮你的吗"
                    }}
                ],
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
                }}
            ],
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
        reply = await gen(user_config[chat_type][id]["messages"], model, api_key, api_url)
        logger.debug(reply)

        formatted_reply = format_reply(reply)
        reply_msg = need_reply_msg(reply)

        user_config[chat_type][id]["messages"].append({"role": "assistant", "content": f"{reply}"})

        await send_formatted_reply(bot, event, formatted_reply, reply_msg)
        add_cd(id)
        sequence[chat_type].remove(id)
    except Exception as e:
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
            user_config = data

# 定义关闭时的钩子函数，用于保存用户配置
@driver.on_shutdown
async def _():
    if save_user_config:
        write_all_data(user_config)    
    