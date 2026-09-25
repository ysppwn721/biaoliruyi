"""只读工具注册表：把知链已有能力提供给 MCP 和其他 Agent。"""
from __future__ import annotations

import datetime as _datetime
from decimal import Decimal
from pathlib import Path

from . import engine, office
from .diagnose import diagnose


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (Path, _datetime.date, _datetime.datetime, _datetime.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return '<binary data omitted>'
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _safe(handler):
    def wrapped(store, params):
        try:
            return _json_safe(handler(store, params))
        except Exception:
            return {'error': '操作失败，请检查输入参数、项目状态和文件内容。'}
    return wrapped


def _list_projects(store, params):
    return {'projects': store.list()}


def _parse_facts(store, params):
    path = Path(params['excel_path'])
    return {'facts': office.read_facts(path, engine.stable_id(path))}


def _parse_document(store, params):
    excel = Path(params['excel_path'])
    document = Path(params['document_path'])
    facts = office.read_facts(excel, engine.stable_id(excel))
    blocks, charts, warnings = office.read_document(document, engine.stable_id(document), facts)
    claims = []
    for block in blocks:
        claims.extend(engine.extract_claims(block, facts))
    return {'blocks': blocks, 'claims': claims, 'charts': charts, 'warnings': warnings}


def _verify_claim(store, params):
    return engine.check(params['claim'], params['facts'])


def _verify_project(store, params):
    workspace = store.read(params['project_id'])
    checks, summary = engine.inspect(workspace)
    return {'checks': checks, 'summary': summary}


def _diagnose_project(store, params):
    workspace = store.read(params['project_id'])
    checks, _ = engine.inspect(workspace)
    records, summary = diagnose(workspace, checks)
    return {'records': records, 'summary': summary}


def _diff_excel(store, params):
    workspace = store.read(params['project_id'])
    return store.preview_source(params['project_id'], workspace['revision'], params['excel_path'])


_ID_SCHEMA = {'type': 'string', 'description': '32位项目ID'}
_PATH_SCHEMA = {'type': 'string', 'description': '绝对路径字符串'}
_CLAIM_SCHEMA = {'type': 'object', 'additionalProperties': True,
                 'description': 'engine.extract_claims 返回的论断对象'}
_FACTS_SCHEMA = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': True},
                 'description': 'office.read_facts 返回的事实对象数组'}

TOOLS = [
    {'name': 'list_projects', 'description': '列出知链工作区中的全部项目（id、名称、创建时间、版本）。',
     'input_schema': {'type': 'object', 'properties': {}, 'required': []}, 'handler': _safe(_list_projects)},
    {'name': 'parse_facts', 'description': '解析绝对路径中的 Excel 事实表。',
     'input_schema': {'type': 'object', 'properties': {'excel_path': _PATH_SCHEMA}, 'required': ['excel_path']},
     'handler': _safe(_parse_facts)},
    {'name': 'parse_document', 'description': '解析 Word/PPT 并抽取规则支持的论断。',
     'input_schema': {'type': 'object', 'properties': {'excel_path': _PATH_SCHEMA, 'document_path': _PATH_SCHEMA},
                      'required': ['excel_path', 'document_path']}, 'handler': _safe(_parse_document)},
    {'name': 'verify_claim', 'description': '使用确定性规则核验单条论断；claim 和 facts 结构见解析工具返回值。',
     'input_schema': {'type': 'object', 'properties': {'claim': _CLAIM_SCHEMA, 'facts': _FACTS_SCHEMA},
                      'required': ['claim', 'facts']}, 'handler': _safe(_verify_claim)},
    {'name': 'verify_project', 'description': '核验项目中的全部已识别论断。',
     'input_schema': {'type': 'object', 'properties': {'project_id': _ID_SCHEMA}, 'required': ['project_id']},
     'handler': _safe(_verify_project)},
    {'name': 'diagnose_project', 'description': '生成项目全部论断的异常分类、解释和证据溯源。',
     'input_schema': {'type': 'object', 'properties': {'project_id': _ID_SCHEMA}, 'required': ['project_id']},
     'handler': _safe(_diagnose_project)},
    {'name': 'diff_excel', 'description': '预览新 Excel 对项目的影响，不写入项目版本。',
     'input_schema': {'type': 'object', 'properties': {'project_id': _ID_SCHEMA, 'excel_path': _PATH_SCHEMA},
                      'required': ['project_id', 'excel_path']}, 'handler': _safe(_diff_excel)},
]

TOOL_MAP = {tool['name']: tool for tool in TOOLS}


def invoke(store, name, params):
    """按名称调用只读工具，返回 JSON 可序列化对象。"""
    if name not in TOOL_MAP:
        return {'error': '工具不存在。'}
    return TOOL_MAP[name]['handler'](store, params)
