import time
from .config import chat_cd

cd = {}


def add_cd(uid: str):
    if uid not in cd:
        cd[uid] = 0
    cd[uid] = time.time() + chat_cd


def check_cd(uid: str):
    if uid not in cd:
        return True
    return time.time() > cd[uid]
