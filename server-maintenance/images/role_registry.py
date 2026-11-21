"""Trusted local configuration for reusable QQ capabilities."""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Role:
    name: str
    config: Path
    runtime: Path
    port: int
    model: str
    handles_owner: bool


def roles_from(data):
    owner = str(data['owner'])
    if not re.fullmatch(r'[1-9][0-9]{3,15}', owner):
        raise ValueError('invalid_owner')
    home = Path('/home/ubuntu')
    legacy = {13001: ('qq-codex','bridge/.private/config.json','codex'),
              13101: ('qq-dsh','napcat-runtime/.private/bridge-config.json','deepseek')}
    roles = {}
    ports = set()
    paths = set()
    for bot, item in data['accounts'].items():
        port = item['port']
        if (not re.fullmatch(r'[1-9][0-9]{3,15}',bot) or bot == owner or type(port) is not int
                or not 1024 <= port <= 65535 or port in ports or not str(item['name']).strip()):
            raise ValueError('invalid_account')
        if port in legacy:
            directory, relative, model = legacy[port]
            root = home/directory
            config = root/relative
            if item.get('config') != config.as_posix() or 'role' in item:
                raise ValueError('unexpected_legacy_config')
            handles_owner = False
        else:
            slug = item.get('role','')
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',slug) or 'config' in item:
                raise ValueError('invalid_role')
            root = home/'qq-roles'/slug
            config = root/'bridge/.private/config.json'
            model = item.get('model','codex')
            if model not in ('codex','deepseek'):
                raise ValueError('invalid_model')
            handles_owner = True
        if config in paths:
            raise ValueError('duplicate_role')
        paths.add(config)
        ports.add(port)
        roles[bot] = Role(item['name'],config,root/'napcat-runtime',port,model,handles_owner)
    if not roles:
        raise ValueError('empty_accounts')
    return owner,roles


def check_binding(role, config, bot, owner):
    if (str(config.get('bot_qq')) != bot or str(config.get('owner_qq')) != owner
            or config.get('onebot_url') != f'http://127.0.0.1:{role.port}'):
        raise ValueError('role_identity_mismatch')
