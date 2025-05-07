from pydantic import BaseModel, Field
from nonebot import get_plugin_config


class ModelConfig(BaseModel):
    name: str = Field(..., description="模型对外公开名称")
    description: str = Field("", description="模型对外公开描述")
    api_url: str = Field(..., description="API地址")
    api_key: str = Field(..., description="API Key")
    model_name: str = Field(..., description="模型名称")
    send_thinking: bool = Field(
        False, description="发送思考内容，如果有（仅在支持模型上有效，如deepseek-r1）"
    )
    image_input: bool = Field(
        False, description="是否支持输入图片（适用于多模态模型，如qwen-vl）"
    )


class CompletionConfig(BaseModel):
    max_token: int = Field(1024, description="最大输出token数")
    temperature: float = Field(0.7, description="temperature")
    top_p: float = Field(0.9, description="top_p")


class MemeConfig(BaseModel):
    url: str = Field(..., description="表情包地址")
    desc: str = Field(..., description="表情包描述")

class TTSConfig(BaseModel):
    api_url: str = Field("https://api.fish.audio", description="FishAudio API地址")
    api_key: str = Field(..., description="API Key")
    reference_id: str = Field(..., description="音色的 Reference ID")
    speed: float = Field(1.0, description="语速")
    volume: float = Field(0.0, description="音量")

class Config(BaseModel):
    aitalk_command_start: str = Field("", description="对话触发前缀")
    aitalk_api_list: list[ModelConfig] = Field(..., description="API配置")
    aitalk_default_prompt: str = Field(
        "你的回答应该尽量简洁、幽默、可以使用一些语气词、颜文字。你应该拒绝回答任何政治相关的问题。",
        description="默认提示词，和默认提示词文件二选一，优先使用文件",
    )
    aitalk_completion_config: CompletionConfig = Field(
        default_factory=CompletionConfig, description="生成配置"
    )
    aitalk_default_prompt_file: str = Field(
        "",
        description="默认提示词文件路径 (相对于机器人运行根目录)，和默认提示词二选一，优先使用文件",
    )

    # 新增：群聊专属提示词文件存放目录
    aitalk_group_prompts_dir: str = Field(
        "./aitalk_config/group_prompts",
        description="群聊专属提示词文件存放目录 (例如: ./aitalk_config/group_prompts/12345.txt)。路径相对于机器人运行根目录。",
    )

    aitalk_available_memes: list[MemeConfig] = Field(..., description="可用表情包")
    aitalk_reply_when_meme: bool = Field(
        False, description="当发送表情包时是否回复原消息"
    )
    aitalk_reply: bool = Field(True, description="是否回复原消息")
    aitalk_max_split_length: int = Field(5, description="消息最大分割长度")
    aitalk_max_context_length: int = Field(20, description="最大上下文长度")
    aitalk_save_user_config: bool = Field(
        True, description="是否在关闭时保存用户配置，重启后会进行读取"
    )
    aitalk_default_available: bool = Field(True, description="是否默认启用（群聊）")
    aitalk_default_available_private: bool = Field(
        True, description="是否默认启用（私聊）"
    )
    aitalk_chat_cd: int = Field(5, description="冷却cd,单位为秒")

    aitalk_tts_enabled: bool = Field(False, description="是否启用TTS语音合成")
    aitalk_tts_config: TTSConfig = Field(
        default_factory=TTSConfig, description="TTS语音合成配置"
    )


plugin_config = get_plugin_config(Config)  # 加载插件配置
command_start = plugin_config.aitalk_command_start
api_list = plugin_config.aitalk_api_list
default_prompt = plugin_config.aitalk_default_prompt
default_prompt_file = plugin_config.aitalk_default_prompt_file
available_memes = plugin_config.aitalk_available_memes
reply_when_meme = plugin_config.aitalk_reply_when_meme
reply_msg = plugin_config.aitalk_reply
max_split_length = plugin_config.aitalk_max_split_length
max_context_length = plugin_config.aitalk_max_context_length
save_user_config = plugin_config.aitalk_save_user_config
default_available = plugin_config.aitalk_default_available
default_available_private = plugin_config.aitalk_default_available_private
chat_cd = plugin_config.aitalk_chat_cd
group_prompts_dir = plugin_config.aitalk_group_prompts_dir
tts_enabled = plugin_config.aitalk_tts_enabled
tts_config = plugin_config.aitalk_tts_config
