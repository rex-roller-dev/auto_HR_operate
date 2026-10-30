"""旧项目refresh_token.py兼容桥接。

将volunteer_yearly项目的yearly目录放到旧项目可导入的位置，
再用本文件替换旧refresh_token.py。两服务的TOKEN_*环境变量必须一致。
"""
from pathlib import Path  # 旧main.py曾通过import *间接使用Path。
import time
from yearly.config import Settings
from yearly.cosio import CosStore, client_from_env
from yearly.tokens import TokenManager


def _manager():
    cfg = Settings.from_env()
    client = client_from_env(cfg.cos_region)
    return TokenManager(CosStore(client, cfg.token_bucket or cfg.cos_bucket), cfg)


def get_access_token():
    manager = _manager()
    token = manager.get()
    # 保持旧调用签名(access_token, refresh_token)。
    return token, manager._current().get("refresh_token")


def save_token(token_data):
    return _manager().save_authorization(token_data)


def load_token():
    return _manager()._current()


def token_expired(token_data):
    return not TokenManager._valid(token_data)


def refresh_token(refresh_token):
    # 以COS中的最新Token为准，不使用调用者可能已经过时的refresh_token。
    manager = _manager()
    manager.get()
    return manager._current()
