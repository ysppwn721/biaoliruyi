"""知链 HTTP API and static workbench."""
from __future__ import annotations

import base64
import hmac
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .demo import create_demo
from .llm import config, suggest_links
from .store import Store, now

BASE = Path(__file__).resolve().parent.parent


def load_environment():
    """Simple KEY=VALUE file; no interpolation, execution, or secret logging."""
    env = BASE / '.env'
    if env.exists():
        for raw in env.read_text(encoding='utf-8-sig').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            if re.fullmatch(r'[A-Z][A-Z0-9_]*', key.strip()):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Link(BaseModel):
    claim_id: str
    refs: list[str] = Field(max_length=2000)


class LinksRequest(BaseModel):
    revision: int
    links: list[Link] = Field(max_length=500)


class ChangeRequest(BaseModel):
    revision: int
    values: dict[str, float]


class RepairRequest(BaseModel):
    revision: int
    claim_ids: list[str] = Field(max_length=500)


class RevisionRequest(BaseModel):
    revision: int


def create_app(data_dir=None):
    load_environment()
    store = Store(data_dir or os.getenv('ZHILIAN_DATA_DIR', str(BASE / '.zhilian')))
    app = FastAPI(title='知链', version='0.2.0', description='跨文档结论验证与增量修复')
    app.state.store = store

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        password = os.getenv('ZHILIAN_ACCESS_PASSWORD', '')
        if password:
            valid = False
            try:
                scheme, token = request.headers.get('authorization', '').split(' ', 1)
                user, supplied = base64.b64decode(token, validate=True).decode().split(':', 1)
                valid = scheme.lower() == 'basic' and hmac.compare_digest(supplied.encode(), password.encode()) and user == 'zhilian'
            except (ValueError, UnicodeError):
                pass
            if not valid:
                return JSONResponse({'detail': '请使用用户名 zhilian 与部署密码登录'}, status_code=401,
                                    headers={'WWW-Authenticate': 'Basic realm="Zhilian", charset="UTF-8"'})
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail': '拒绝跨站修改请求'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({'detail': '项目或文件不存在'}, status_code=404)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'version': '0.2.0', 'model': config(),
                'password_protected': bool(os.getenv('ZHILIAN_ACCESS_PASSWORD'))}

    @app.get('/api/projects')
    def projects():
        return store.list()

    @app.post('/api/projects/demo')
    def demo():
        with tempfile.TemporaryDirectory() as tmp:
            return store.create('销售分析 · 演示项目', create_demo(tmp), demo=True)

    @app.get('/api/template')
    def template():
        folder = store.root / '_templates'
        if not (folder / '业务数据.xlsx').exists():
            create_demo(folder)
        return FileResponse(folder / '业务数据.xlsx', filename='知链事实表模板.xlsx')

    @app.post('/api/projects')
    async def upload(name: str = Form('新项目'), files: list[UploadFile] = File(...)):
        if len(files) > 10:
            raise ValueError('最多上传10份文件')
        paths, total, names = [], 0, set()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                for f in files:
                    filename = (f.filename or '').replace('\\', '/').split('/')[-1]
                    if not filename or filename in names or Path(filename).suffix.lower() not in ('.xlsx', '.docx', '.pptx'):
                        raise ValueError('文件名重复或类型不受支持，仅接受xlsx、docx、pptx')
                    if len(filename) > 150 or any(c in filename for c in '<>:"|?*'):
                        raise ValueError('文件名无效或过长')
                    names.add(filename)
                    path = Path(tmp) / filename
                    with path.open('wb') as out:
                        while chunk := await f.read(1024 * 1024):
                            total += len(chunk)
                            if total > 30 * 1024 * 1024:
                                raise ValueError('每批上传总大小不超过30MB')
                            out.write(chunk)
                    paths.append(path)
                return await run_in_threadpool(store.create, name, paths)
            finally:
                for f in files:
                    await f.close()

    @app.get('/api/projects/{wid}')
    def get_project(wid: str):
        with store.lock:
            return store.public(store.read(wid))

    @app.post('/api/projects/{wid}/links')
    def confirm(wid: str, body: LinksRequest):
        return store.confirm(wid, body.revision, [i.model_dump() for i in body.links])

    @app.post('/api/projects/{wid}/facts')
    def change(wid: str, body: ChangeRequest):
        return store.change(wid, body.revision, body.values)

    async def uploaded_source(wid, revision, file, operation):
        try:
            if Path(file.filename or '').suffix.lower() != '.xlsx':
                raise ValueError('请选择保存后的 .xlsx 文件')
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'updated.xlsx'
                total = 0
                with path.open('wb') as out:
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > 30 * 1024 * 1024:
                            raise ValueError('更新表不超过30MB')
                        out.write(chunk)
                return await run_in_threadpool(operation, wid, revision, path)
        finally:
            await file.close()

    @app.post('/api/projects/{wid}/source/preview')
    async def preview_source(wid: str, revision: int = Form(...), file: UploadFile = File(...)):
        return await uploaded_source(wid, revision, file, store.preview_source)

    @app.post('/api/projects/{wid}/source')
    async def import_source(wid: str, revision: int = Form(...), file: UploadFile = File(...)):
        return await uploaded_source(wid, revision, file, store.import_source)

    @app.post('/api/projects/{wid}/repair')
    def repair(wid: str, body: RepairRequest):
        return store.repair(wid, body.revision, body.claim_ids)

    @app.post('/api/projects/{wid}/undo')
    def undo(wid: str, body: RevisionRequest):
        return store.undo(wid, body.revision)

    @app.post('/api/projects/{wid}/suggest')
    def suggestions(wid: str, body: RevisionRequest):
        with store.lock:
            ws = store.read(wid)
            store.verify(ws, body.revision)
        result = suggest_links(ws['claims'], ws['facts'])
        with store.lock:
            ws = store.read(wid)
            store.verify(ws, body.revision)
            ws['suggestions'] = result
            ws['revision'] += 1
            ws['audit'].append({'time': now(), 'event': '模型建议', 'detail': f'模型 {config()["model"]} 提出{len(result)}项建议，尚未确认'})
            store.write(ws)
            return store.public(ws)

    @app.get('/api/projects/{wid}/files/{fid}')
    def download(wid: str, fid: str):
        ws = store.read(wid)
        store.verify(ws, ws['revision'])
        d = next((d for d in ws['documents'] if d['id'] == fid), None)
        if not d:
            raise HTTPException(404, '文件不存在')
        return FileResponse(store.folder(wid) / ws['generation'] / d['stored_name'], filename=d['name'])

    @app.get('/api/projects/{wid}/export')
    def export(wid: str):
        return FileResponse(store.archive(wid), filename='知链成果与核验记录.zip', media_type='application/zip')

    @app.get('/')
    def index():
        return FileResponse(BASE / 'web' / 'index.html')

    app.mount('/static', StaticFiles(directory=BASE / 'web'), name='static')
    return app


app = create_app()
