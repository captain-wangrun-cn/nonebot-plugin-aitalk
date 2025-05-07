import nonebot_plugin_localstore as store
from pathlib import Path
import json
from .config import default_available, default_available_private


def get_config_file() -> Path:
    file = store.get_plugin_config_file("config.json")
    if not file.exists():
        file.write_text("{}")
    return file


def get_available_config_file() -> Path:
    file = store.get_plugin_config_file("available.json")
    if not file.exists():
        file.write_text("{}")
    return file


def get_available_private_config_file():
    file = store.get_plugin_config_file("available_private.json")
    if not file.exists():
        file.write_text("{}")
    return file


def write_data(key, value):
    file = get_config_file()
    data = json.loads(file.read_text())
    data[key] = value
    file.write_text(json.dumps(data))


def write_all_data(data):
    file = get_config_file()
    file.write_text(json.dumps(data))


def read_data(key):
    file = get_config_file()
    data = json.loads(file.read_text())
    return data.get(key)


def read_all_data():
    file = get_config_file()
    data = json.loads(file.read_text())
    return data


def enable(gid: int):
    file = get_available_config_file()
    data = json.loads(file.read_text())
    data[str(gid)] = True
    file.write_text(json.dumps(data))


def disable(gid: int):
    file = get_available_config_file()
    data = json.loads(file.read_text())
    data[str(gid)] = False
    file.write_text(json.dumps(data))


def is_available(gid: int):
    file = get_available_config_file()
    data = json.loads(file.read_text())
    if str(gid) not in data:
        return default_available
    return data[str(gid)]


def enable_private(uid: int):
    file = get_available_private_config_file()
    data = json.loads(file.read_text())
    data[str(uid)] = True
    file.write_text(json.dumps(data))


def disable_private(uid: int):
    file = get_available_private_config_file()
    data = json.loads(file.read_text())
    data[str(uid)] = False
    file.write_text(json.dumps(data))


def is_private_available(uid: int):
    file = get_available_private_config_file()
    data = json.loads(file.read_text())
    if str(uid) not in data:
        return default_available_private
    return data[str(uid)]
