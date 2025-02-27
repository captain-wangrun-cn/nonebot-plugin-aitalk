<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <img src="https://github.com/WStudioGroup/hifumi-plugins/blob/main/remove.photos-removed-background.png" width="200">
  <br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-aitalk

_✨ 简单好用的AI聊天插件 ✨_


<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/captain-wangrun-cn/nonebot-plugin-aitalk.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-aitalk">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-aitalk.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">

</div>

## 📖 介绍

简单好用的AI聊天插件，支持多API，支持发送表情包，艾特，戳一戳等

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-aitalk

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

    pip install nonebot-plugin-aitalk
</details>


打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_aitalk"]

</details>

## ⚙️ 配置

在 nonebot2 项目的`.env`文件中添加下表中的必填配置

| 配置项          | 类型   | 必填 | 默认值 | 说明                  |
|:------------:|:----:|:---:|:---:|:-------------------:|
| aitalk_api_list | list | 是 | [ ] | API列表，支持多个API，格式请往下看 |
| aitalk_available_memes | list | 是 | [ ] | AI可以发送的表情包，格式请往下看 |
| aitalk_command_start | str | 否  | ""  | 对话触发前缀，例如“/对话”，类似on_command，为空时直接艾特即可触发 |
| aitalk_completion_config | list | 否 | [ ] | 生成配置，格式请往下看 |
| aitalk_default_prompt | str | 否 | "你的回答应该尽量简洁、幽默、可以使用一些语气词、颜文字。你应该拒绝回答任何政治相关的问题。" | 默认提示词 |
| aitalk_default_prompt_file | str | 否 | "" | 默认提示词文件路径，与提示词二选一，优先使用文件。请注意将windows系统路径中的\替换成\\ |
| aitalk_reply_when_meme | bool | 否 | true | 当只有表情包时，是否回复消息 |
| aitalk_max_split_length | int | 否 | 5 | 最大分割长度，将会在prompt中告诉ai，回复的消息数量不要大于这个值，可能不起作用 |
| aitalk_max_context_length | int | 否 | 20 | 最长上下文消息数量，超过这个数量时，将会逐个抛弃最早的一条消息。这个数值包括设定消息 |
| aitalk_save_user_config | bool | 否 | true | 是否保存用户配置，关闭nonebot时将会保存用户所选模型，对话内容等，启动时读取 |
| aitalk_default_available | bool | 否 | true | 是否默认允许群聊使用，为false时需要手动使用指令开启 |
| aitalk_default_available_private | bool | 否 | true | 是否默认允许私聊使用，为false时需要手动使用指令开启 |
| aitalk_chat_cd | int | 否 | 5 | 聊天cd，单位秒 |


aitalk_api_list（api列表）格式：
```json
[
{
    "name": "向用户展示的模型名称",
    "api_key": "你的api key",
    "model_name": "请求api用的模型名称",
    "api_url": "api接口地址"
},
{
    "name": "向用户展示的模型名称2",
    "api_key": "你的api key2",
    "model_name": "请求api用的模型名称2",
    "api_url": "api接口地址2"
}
]
```


aitalk_completion_config（生成配置）格式：
```json
{
    "max_token": 1024,
    "temperature": 0.7
    "top_p": 0.9
}
```


aitalk_available_memes（AI可以发送的表情包）格式：
```json
[
{
    "url": "图片地址，支持链接或本地路径。⚠️⚠️注意！如果是windows系统的本地路径，请将路径中的\换成/，可以看下面的配置示例⚠️⚠️",
    "desc": "图片描述，告诉AI这张表情包是什么内容，用于什么场景等等"
},
{
    "url": "图片地址2",
    "desc": "图片描述2"
}
]
```


## ⚙️ 配置示例
```
aitalk_api_list = '
[
{
    "name": "deepseekr1-14b",
    "api_key": "sk-1145141919810",
    "model_name": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    "api_url": "https://api.siliconflow.cn/v1"
},
{
    "name": "gemma-27b",
    "api_key": "sk-1145141919810",
    "model_name": "google/gemma-2-27b-it",
    "api_url": "https://api.siliconflow.cn/v1"
},
{
    "name": "千问2.5-14b",
    "api_key": "sk-1145141919810",
    "model_name": "Qwen/Qwen2.5-14B-Instruct",
    "api_url": "https://api.siliconflow.cn/v1"
},
{
    "name": "chatgpt-4o",
    "api_key": "sk-1145141919810",
    "model_name": "gpt-4o",
    "api_url": "https://api.aiskt.com/v1"
}
]
'
aitalk_available_memes = '
[
{
    "url": "D:/bots/imgs/1.png",
    "desc": "很抱歉伤害到你"
},
{
    "url": "D:/bots/imgs/2.png",
    "desc": "哭"
},
{
    "url": "D:/bots/imgs/3.png",
    "desc": "啊哈哈...（感到尴尬）"
}
]
'
aitalk_default_prompt_file = "D:\\prompt\\日富美.txt"
```



## 🎉 使用
### 指令表
| 指令 | 权限 | 需要@ | 范围 | 说明 |
|:-----:|:----:|:----:|:----:|:----:|
| @机器人 | 群聊 | 是 | 群聊 | 艾特机器人即可聊天 |
| 模型选择 | 群聊 | 否 | 群聊 | 选择模型 |
| ai对话 开启 | 管理员+ | 否 | 群聊 | 开启本群ai对话 |
| ai对话 关闭 | 管理员+ | 否 | 群聊 | 关闭本群ai对话 |
| 清空聊天记录 | 群聊 | 否 | 群聊 | 清空对话记录 |
### 效果图
<img src="imgs/QQ20250222-232704.png">
<img src="imgs/QQ20250222-232730.png">
<img src="imgs/QQ20250222-232813.png">

## 🍟参考
[nonebot-plugin-llmchat](https://github.com/FuQuan233/nonebot-plugin-llmchat) 参考了部分代码以及prompt

## 📃 更新日志
### 1.0.8（2025.02.28）
- ❤️添加了私聊聊天支持
### 1.0.7（2025.02.25）
- ❤️更改data.py
### 1.0.6（2025.02.23）
- 😡排除Q群管家
### 1.0.5（2025.02.23）
- 🧋修复了表情包链接问题
### 1.0.4（2025.02.23）
- 🧋修复一些问题,更改README
### 1.0.3（2025.02.23）
- 🧋修复依赖问题
### 1.0.2（2025.02.23）
- 🧋修复表情包本地路径问题
### 1.0.1（2025.02.22）
- 🧋更新README
### 1.0.0（2025.02.22）
- 🧋发布
