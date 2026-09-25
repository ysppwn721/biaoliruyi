"""知链只读 MCP stdio 服务器。"""
from __future__ import annotations

import os
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import tools
from .app import BASE, load_environment
from .store import Store


def build_mcp():
    load_environment()
    store = Store(os.getenv('ZHILIAN_DATA_DIR', str(BASE / '.zhilian')))
    mcp = FastMCP('zhilian', instructions='知链：跨文档结论验证与增量修复工具。只读核验与诊断。')

    def list_projects() -> dict:
        return tools.invoke(store, 'list_projects', {})

    def parse_facts(excel_path: Annotated[str, Field(description='Excel 文件绝对路径')]) -> dict:
        return tools.invoke(store, 'parse_facts', {'excel_path': excel_path})

    def parse_document(excel_path: Annotated[str, Field(description='Excel 文件绝对路径')],
                       document_path: Annotated[str, Field(description='Word 或 PPT 文件绝对路径')]) -> dict:
        return tools.invoke(store, 'parse_document', {'excel_path': excel_path, 'document_path': document_path})

    def verify_claim(claim: Annotated[dict, Field(description='engine.extract_claims 返回的论断对象')],
                     facts: Annotated[list[dict], Field(description='office.read_facts 返回的事实对象数组')]) -> dict:
        return tools.invoke(store, 'verify_claim', {'claim': claim, 'facts': facts})

    def verify_project(project_id: Annotated[str, Field(description='32位项目ID')]) -> dict:
        return tools.invoke(store, 'verify_project', {'project_id': project_id})

    def diagnose_project(project_id: Annotated[str, Field(description='32位项目ID')]) -> dict:
        return tools.invoke(store, 'diagnose_project', {'project_id': project_id})

    def diff_excel(project_id: Annotated[str, Field(description='32位项目ID')],
                  excel_path: Annotated[str, Field(description='新 Excel 文件绝对路径')]) -> dict:
        return tools.invoke(store, 'diff_excel', {'project_id': project_id, 'excel_path': excel_path})

    for fn in (list_projects, parse_facts, parse_document, verify_claim,
               verify_project, diagnose_project, diff_excel):
        mcp.add_tool(fn, description=tools.TOOL_MAP[fn.__name__]['description'], structured_output=False)
    return mcp


def main():
    build_mcp().run(transport='stdio')


if __name__ == '__main__':
    main()
