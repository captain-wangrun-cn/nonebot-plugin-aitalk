from pydantic import BaseModel, Field
from nonebot import get_plugin_config

class ModelConfig(BaseModel):
    name: str = Field(..., description="模型对外公开名称")
    api_url: str = Field(..., description="API地址")
    api_key: str = Field(..., description="API Key")
    model_name: str = Field(..., description="模型名称")

class CompletionConfig(BaseModel):
    max_token: int = Field(1024, description="最大输出token数")
    temperature: float = Field(0.7, description="temperature")
    top_p: float = Field(0.9, description="top_p")

class MemeConfig(BaseModel):
    url: str = Field(..., description="表情包地址")
    desc: str = Field(..., description="表情包描述")

class Config(BaseModel):
    aichat_command_start: str = Field("", description="对话触发前缀")
    aichat_api_list: list[ModelConfig] = Field(..., description="API配置")
    aichat_default_prompt: str = Field(
        "你的回答应该尽量简洁、幽默、可以使用一些语气词、颜文字。你应该拒绝回答任何政治相关的问题。", 
        description="默认提示词，和默认提示词文件二选一，优先使用文件"
    )
    aichat_completion_config: CompletionConfig = Field(
        default_factory=CompletionConfig, 
        description="生成配置"
    )
    aichat_default_prompt_file: str = Field("", description="默认提示词文件，和默认提示词二选一，优先使用文件")
    aichat_available_memes: list[MemeConfig] = Field(..., description="可用表情包")
    aichat_reply_when_meme: bool = Field(False, description="当发送表情包时是否回复原消息")
    aichat_max_split_length: int = Field(5, description="消息最大分割长度")
    aichat_max_context_length: int = Field(20, description="最大上下文长度")
    aichat_save_user_config: bool = Field(True, description="是否在关闭时保存用户配置，重启后会进行读取")
    aichat_default_available: bool = Field(True, description="是否默认启用")
    aichat_chat_cd: int = Field(5, description="冷却cd,单位为秒")

plugin_config = get_plugin_config(Config)
command_start = plugin_config.aichat_command_start
api_list = plugin_config.aichat_api_list
default_prompt = plugin_config.aichat_default_prompt
default_prompt_file = plugin_config.aichat_default_prompt_file
available_memes = plugin_config.aichat_available_memes
reply_when_meme = plugin_config.aichat_reply_when_meme
max_split_length = plugin_config.aichat_max_split_length
max_context_length = plugin_config.aichat_max_context_length
save_user_config = plugin_config.aichat_save_user_config
default_available = plugin_config.aichat_default_available
chat_cd = plugin_config.aichat_chat_cd
