# 戳一戳
class PokeMessage:
    gid = 0
    uid = 0

# 禁言
class BanUser:
    # 群号
    gid = 0
    # 用户号
    uid = 0
    # 禁言时间,单位是秒
    duration = 0

# 语音合成
class TTSMessage:
    # 文本内容
    text = ""
    # 音色id
    reference_id = ""
    # 速度
    speed = 0
    # 音量
    volume = 0
