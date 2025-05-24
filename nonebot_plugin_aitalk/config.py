from pydantic import BaseModel, Field
from nonebot import get_plugin_config
from typing import Dict  # 新增导入 Dict


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


# 新增：分群主动回复配置模型
class GroupActiveReplyConfig(BaseModel):
    keywords: list[str] = Field(description="该群聊的主动回复触发关键字列表")
    probability: float = Field(
        description="该群聊满足关键字后，触发主动回复的概率 (0.0 到 1.0)"
    )
    no_keyword_probability: float = Field(
        description="该群聊未满足关键字时，触发主动回复的概率 (0.0 到 1.0)"
    )


class Config(BaseModel):
    aitalk_default_model: str = Field("", description="默认选择的模型名称")
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
    # 新增：消息发送延迟配置
    aitalk_message_send_delay_min: float = Field(
        0.2, description="发送多条消息时，每条之间的最小延迟（秒），设为0则不延迟"
    )
    aitalk_message_send_delay_max: float = Field(
        1.2, description="发送多条消息时，每条之间的最大延迟（秒）"
    )

    # 主动回复功能配置
    aitalk_active_reply_enabled: bool = Field(False, description="是否启用主动回复功能")
    aitalk_active_reply_keywords: list[str] = Field(
        [],
        description="全局主动回复的触发关键字列表, 例如 ['问题', '请问', '大佬']",  # 修改描述以区分全局
    )
    aitalk_active_reply_probability: float = Field(
        0.3,
        description="全局满足关键字后，触发主动回复的概率 (0.0 到 1.0)",  # 修改描述以区分全局
    )
    aitalk_active_reply_no_keyword_probability: float = Field(
        0.05,
        description="全局未满足关键字时，触发主动回复的概率 (0.0 到 1.0)，建议设置较低的值",  # 修改描述以区分全局
    )
    aitalk_active_reply_context_timeout: int = Field(
        300, description="机器人主动回复后，上下文的有效时间（秒）"
    )
    aitalk_active_reply_max_unrelated_followups: int = Field(  # 新增配置项
        3,
        description="在主动回复上下文中，AI连续判断N次与追问无关后，关闭本次主动回复会话 (0表示不启用此功能)",
    )
    # 分群主动回复配置
    aitalk_group_active_reply_configs: Dict[str, GroupActiveReplyConfig] = Field(
        default_factory=dict,
        description='分群独立主动回复配置。键为群号字符串，值为该群的特定配置。例如：\'{"12345": {"keywords": ["help", "support"], "probability": 0.8, "no_keyword_probability": 0.2}}\'',
    )
    # 是否禁用“忙碌/频繁操作”提示
    aitalk_disable_busy_prompts: bool = Field(
        False,
        description="是否关闭诸如“不要着急哦！”或“你的操作太频繁了哦！”之类的提示信息",
    )


plugin_config = get_plugin_config(Config)  # 加载插件配置
default_model = plugin_config.aitalk_default_model
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
message_send_delay_min = plugin_config.aitalk_message_send_delay_min
message_send_delay_max = plugin_config.aitalk_message_send_delay_max

# 主动回复相关配置加载
active_reply_enabled = plugin_config.aitalk_active_reply_enabled
active_reply_keywords = plugin_config.aitalk_active_reply_keywords  # 这是全局默认值
active_reply_probability = (
    plugin_config.aitalk_active_reply_probability
)  # 这是全局默认值
active_reply_no_keyword_probability = (
    plugin_config.aitalk_active_reply_no_keyword_probability  # 这是全局默认值
)
active_reply_context_timeout = plugin_config.aitalk_active_reply_context_timeout
active_reply_max_unrelated_followups = (
    plugin_config.aitalk_active_reply_max_unrelated_followups
)
# 加载分群主动回复配置
group_active_reply_configs = plugin_config.aitalk_group_active_reply_configs
# 加载是否禁用“忙碌/频繁操作”提示的配置项
disable_busy_prompts = plugin_config.aitalk_disable_busy_prompts
