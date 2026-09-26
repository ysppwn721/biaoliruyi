"""模型调用限额：按访客与全局的双重每日闸门。

演示环境由服务端密钥替使用者付费，而测试账号按大赛要求公开，因此必须限制调用量：
既要防止单个访客刷额度，也要有全局预算上限。触发限额**不是报错**，而是降级为
规则模式——与本项目"没有模型也能完整运行"的能力保持一致，演示不会中断。

计数落在 JSON 文件里（跨进程重启保留），写入使用临时文件 + 原子替换，
当天日期变化时自动清零。文件损坏或缺席按"零消耗"处理，绝不因为限额模块
本身的问题影响演示。
"""
from __future__ import annotations

import json
import os
import threading
from contextvars import ContextVar
from datetime import date
from pathlib import Path

_LOCK = threading.Lock()
_IDENTITY: ContextVar[str] = ContextVar('zhilian_client', default='-')
_PATH: Path | None = None

# 头部优先级：演示环境位于 Cloudflare 之后，真实来源 IP 在 CF-Connecting-IP，
# 若直接取 socket 地址会把所有访客算成同一个（Cloudflare 边缘节点）。
CLIENT_HEADERS = ('cf-connecting-ip', 'x-real-ip', 'x-forwarded-for')


def configure(path) -> None:
    """由 create_app 在拿到数据目录后调用，避免与 store 的目录约定重复。"""
    global _PATH
    _PATH = Path(path)


def _file() -> Path:
    if _PATH is not None:
        return _PATH
    override = os.getenv('ZHILIAN_QUOTA_FILE', '').strip()
    if override:
        return Path(override).expanduser()
    return Path(os.getenv('ZHILIAN_DATA_DIR', '.zhilian')) / 'quota.json'


def config() -> dict:
    return {
        'per_client_limit': int(os.getenv('ZHILIAN_QUOTA_PER_CLIENT', '60')),
        'global_limit': int(os.getenv('ZHILIAN_QUOTA_GLOBAL', '600')),
        'file': str(_file()),
    }


def client_key(headers, fallback: str = '-') -> str:
    """从请求头取出访客标识；取不到时用连接地址。"""
    for name in CLIENT_HEADERS:
        value = (headers.get(name) or '').strip()
        if value:
            return value.split(',')[0].strip()
    return fallback or '-'


def identify(value: str):
    """设置当前请求的访客标识，返回用于复原的 token。"""
    return _IDENTITY.set(value or '-')


def release(token) -> None:
    _IDENTITY.reset(token)


def _load() -> dict:
    today = date.today().isoformat()
    try:
        data = json.loads(_file().read_text(encoding='utf-8'))
        if isinstance(data, dict) and data.get('day') == today:
            clients = {k: int(v) for k, v in (data.get('clients') or {}).items() if isinstance(v, (int, float))}
            return {'day': today, 'global': int(data.get('global') or 0), 'clients': clients}
    except (OSError, ValueError, TypeError):
        pass
    return {'day': today, 'global': 0, 'clients': {}}


def _save(data: dict) -> None:
    path = _file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, path)
    except OSError:
        # 磁盘不可写时不阻断业务流程：本次消耗不持久化，下次仍按旧值判断。
        pass


def snapshot(client: str | None = None) -> dict:
    limits = config()
    with _LOCK:
        data = _load()
    who = _IDENTITY.get() if client is None else client
    used = data['clients'].get(who, 0)
    return {
        'day': data['day'],
        'client': who,
        'client_used': used,
        'client_limit': limits['per_client_limit'],
        'client_remaining': max(0, limits['per_client_limit'] - used),
        'global_used': data['global'],
        'global_limit': limits['global_limit'],
        'global_remaining': max(0, limits['global_limit'] - data['global']),
    }


def check(client: str | None = None) -> dict:
    """判断当前访客能否再发起一次模型调用；不消耗额度。"""
    state = snapshot(client)
    if state['global_remaining'] <= 0:
        return {'allowed': False, 'code': 'global_exhausted',
                'reason': '今日全局模型调用额度已用完，已降级为规则模式', **state}
    if state['client_remaining'] <= 0:
        return {'allowed': False, 'code': 'client_exhausted',
                'reason': '该访客今日模型调用额度已用完，已降级为规则模式', **state}
    return {'allowed': True, 'code': 'ok', 'reason': '额度充足', **state}


def consume(client: str | None = None, count: int = 1) -> dict:
    """记一次真实调用；返回消耗后的状态。"""
    who = _IDENTITY.get() if client is None else client
    with _LOCK:
        data = _load()
        data['global'] += count
        data['clients'][who] = data['clients'].get(who, 0) + count
        _save(data)
    return snapshot(who)
