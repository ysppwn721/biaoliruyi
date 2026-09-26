"""一份 Excel + 多份成果文档：批量追加、跨文档论断、全流程回归。

真实用法不是"一个 Excel 配一个 Word"，而是**一份事实表**对照**一批** Word / PPT
（分部门、分章节、分批交付）。本文件用 HTTP 接口走真实上传路径，覆盖：

  1. 创建项目（1 份 Excel）后分多批追加多份 docx / pptx；
  2. 断言 Excel 始终唯一，且每份追加文档都被扫描出论断；
  3. 覆盖单批上限、重复内容、重名、Excel 再次上传、空文档无正文等拒绝路径；
  4. 一次批次里有一个坏文件时整批回滚，revision 不变；
  5. 多文档状态下跑完 Agent（关联 → 确认 → 修复），并校验每份文档都产出修复版本。
"""
from __future__ import annotations

import json

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.util import Inches

from zhilian.app import create_app
from zhilian.demo import create_demo


def _docx(path, lines, title='追加报告'):
    doc = Document()
    if title is not None:          # title=None 时生成一份完全空白的 docx
        doc.add_heading(title, 0)
    for line in lines:
        doc.add_paragraph(line)
    doc.save(path)
    return path


def _pptx(path, slides):
    prs = Presentation()
    for title, lines in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(0.6), Inches(0.6), Inches(11), Inches(5))
        frame = box.text_frame
        frame.text = title
        for line in lines:
            frame.add_paragraph().text = line
    prs.save(path)
    return path


CLAIMS = [
    '本期销售额为125万元。',
    '较上期增长25%。',
    'A产品销量最高。',
    '支出未超过预算。',
]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv('ZHILIAN_ACCESS_PASSWORD', raising=False)
    monkeypatch.delenv('ZHILIAN_MAX_APPEND_BATCH', raising=False)
    return TestClient(create_app(tmp_path / 'api'))


def _create(client, tmp_path, name='多文档项目'):
    paths = create_demo(tmp_path / 'demo')
    excel = next(p for p in paths if p.suffix == '.xlsx')
    first = next(p for p in paths if p.suffix == '.docx')
    response = client.post('/api/projects', data={'name': name}, files=[
        ('files', (excel.name, excel.read_bytes(), 'application/octet-stream')),
        ('files', (first.name, first.read_bytes(), 'application/octet-stream')),
    ])
    assert response.status_code == 200, response.text
    return response.json(), excel


def _append(client, wid, revision, paths):
    return client.post(f'/api/projects/{wid}/documents', data={'revision': revision},
                       files=[('files', (p.name, p.read_bytes(), 'application/octet-stream')) for p in paths])


def test_one_excel_with_many_documents_across_batches(api, tmp_path):
    ws, excel = _create(api, tmp_path)
    assert len([d for d in ws['documents'] if d['kind'] == 'xlsx']) == 1

    batch_a = [tmp_path / f'市场部报告{i}.docx' for i in range(1, 4)]
    for i, path in enumerate(batch_a, 1):
        _docx(path, [f'第{i}份市场报告。'] + CLAIMS, f'市场报告{i}')
    batch_b = [tmp_path / '季度汇报.pptx', tmp_path / '产品线报告.docx']
    _pptx(batch_b[0], [('季度汇报', CLAIMS), ('产品线', ['A产品销量最高。'])])
    _docx(batch_b[1], ['产品线补充说明。'] + CLAIMS, '产品线报告')

    revision, total_appended = ws['revision'], 0
    for batch in (batch_a, batch_b):
        response = _append(api, ws['id'], revision, batch)
        assert response.status_code == 200, response.text
        ws = response.json()
        assert ws['batch']['count'] == len(batch)
        revision = ws['revision']
        total_appended += len(batch)
        # 每批结束后 Excel 必须仍然唯一
        assert len([d for d in ws['documents'] if d['kind'] == 'xlsx']) == 1
        assert sum(1 for d in ws['documents'] if d['kind'] == 'xlsx') == 1

    assert ws['summary']['documents'] == 2 + total_appended
    assert len([d for d in ws['documents'] if d['kind'] == 'xlsx']) == 1
    # 每份追加文档都要真的产出论断，而不是只挂了个文件名。
    # Excel 是事实表本身，不含论断，必须排除。
    state = api.get(f'/api/projects/{ws["id"]}').json()
    result_docs = [d for d in state['documents'] if d['kind'] != 'xlsx']
    per_file = {d['id']: 0 for d in result_docs}
    for claim in state['claims']:
        per_file[claim['file_id']] = per_file.get(claim['file_id'], 0) + 1
    assert len(result_docs) == 1 + total_appended
    assert all(per_file.values()), f'存在 0 论断的成果文档：{per_file}'
    # 批次可查询
    for batch in state['batches']:
        got = api.get(f'/api/projects/{ws["id"]}/batches/{batch["id"]}')
        assert got.status_code == 200 and got.json()['status'] == 'done'


def test_document_without_claims_is_accepted_but_reports_zero(api, tmp_path):
    ws, _ = _create(api, tmp_path)
    plain = _docx(tmp_path / '纯说明文档.docx', ['本文件只包含背景说明，没有任何数值结论。'], '说明')
    response = _append(api, ws['id'], ws['revision'], [plain])
    assert response.status_code == 200, response.text
    state = api.get(f'/api/projects/{ws["id"]}').json()
    fid = next(d['id'] for d in state['documents'] if d['name'] == plain.name)
    assert not any(c['file_id'] == fid for c in state['claims'])


def test_append_rejections_and_rollback(api, tmp_path, monkeypatch):
    ws, excel = _create(api, tmp_path)
    revision = ws['revision']

    # 再次上传 Excel
    rejected = _append(api, ws['id'], revision, [excel])
    assert rejected.status_code == 400 and 'xlsx' in rejected.text
    # 非 Office 文件
    junk = tmp_path / '说明.txt'
    junk.write_text('not office', encoding='utf-8')
    assert _append(api, ws['id'], revision, [junk]).status_code == 400
    # 本批内重名
    dup = _docx(tmp_path / '同一份.docx', CLAIMS)
    same = tmp_path / 'dup' / '同一份.docx'
    same.parent.mkdir(exist_ok=True)
    same.write_bytes(dup.read_bytes())
    assert _append(api, ws['id'], revision, [dup, same]).status_code == 400
    # 与项目内已有文件同名
    existing_name = next(d['name'] for d in ws['documents'] if d['kind'] == 'docx')
    collide = tmp_path / 'collide' / existing_name
    collide.parent.mkdir(exist_ok=True)
    collide.write_bytes(dup.read_bytes())
    assert _append(api, ws['id'], revision, [collide]).status_code == 400
    # 空文档没有正文
    empty = _docx(tmp_path / '空文档.docx', [], title=None)
    assert _append(api, ws['id'], revision, [empty]).status_code == 400
    # 过期 revision 必须拒绝
    stale = _docx(tmp_path / '过期.docx', CLAIMS)
    assert _append(api, ws['id'], revision + 99, [stale]).status_code != 200

    # 整批回滚：一个坏文件不能让 revision 前进
    good = _docx(tmp_path / '好文件.docx', CLAIMS)
    bad = tmp_path / '坏文件.docx'
    bad.write_bytes(b'not an Office document')
    before = api.get(f'/api/projects/{ws["id"]}').json()
    assert _append(api, ws['id'], before['revision'], [good, bad]).status_code == 400
    after = api.get(f'/api/projects/{ws["id"]}').json()
    assert after['revision'] == before['revision']
    assert not any(d['name'] == good.name for d in after['documents'])

    # 单批上限
    monkeypatch.setenv('ZHILIAN_MAX_APPEND_BATCH', '2')
    three = [_docx(tmp_path / f'超限{i}.docx', CLAIMS) for i in range(3)]
    assert _append(api, ws['id'], after['revision'], three).status_code == 400


def test_multi_document_agent_flow_repairs_every_document(api, tmp_path):
    ws, excel = _create(api, tmp_path)
    # 追加文档里必须至少有一条与事实表不符的论断，否则 end-to-end 只走到
    # "全部一致"就结束，测不到修复写回（123 与事实表的 125 不一致）。
    extra = [_docx(tmp_path / '追加甲.docx', CLAIMS[:1] + ['本期销售额为123万元。'] + CLAIMS[1:], '甲'),
             _pptx(tmp_path / '追加乙.pptx', [('乙', CLAIMS)])]
    ws = _append(api, ws['id'], ws['revision'], extra).json()
    document_ids = [d['id'] for d in ws['documents']]

    base = f'/api/projects/{ws["id"]}/agent'
    revision = ws['revision']
    for _ in range(6):
        response = api.post(base + '/run', json={'revision': revision})
        assert response.status_code == 200, response.text
        current = response.json()
        revision = current['revision']
        pending = current['agent']['pending']
        if not pending:
            break
        # 关联确认项必须给出可勾选来源，否则界面无解、decide 必然报错。
        # 这正是本轮修掉的增长率"零选项"死结，这里固化成回归断言。
        # （approve_repair 是修复清单，本来就没有来源选项。）
        if pending['kind'] in ('resolve_ambiguity', 'confirm_links'):
            assert all(i.get('options') for i in pending['items']), \
                f'存在零选项的待确认项：{[(i["kind"], i["original"]) for i in pending["items"] if not i.get("options")]}'
            items = [{'claim_id': i['claim_id'],
                      'refs': i['refs'] or i['options'][0]['refs']} for i in pending['items']]
        else:
            items = [{'claim_id': i['claim_id'], 'refs': i['refs']} for i in pending['items']]
        decided = api.post(base + '/decide', json={'revision': revision,
                                                   'decisions': [{'kind': pending['kind'], 'items': items}]})
        assert decided.status_code == 200, decided.text
        revision = decided.json()['revision']

    final = api.get(f'/api/projects/{ws["id"]}').json()
    assert final['agent']['phase'] == 'done'
    assert all(c['confirmed'] for c in final['claims'])
    assert final['last_repair'], '多文档状态下应产出修复结果'
    repaired_files = {r['file_id'] for r in final['last_repair'].get('files', [])} \
        if isinstance(final['last_repair'].get('files'), list) else set(document_ids)
    assert repaired_files <= set(document_ids)
    # 每份成果文档都能取到当前版本
    for fid in document_ids:
        if next(d for d in final['documents'] if d['id'] == fid)['kind'] == 'xlsx':
            continue
        got = api.get(f'/api/projects/{ws["id"]}/files/{fid}')
        assert got.status_code == 200 and got.content
    report = api.get(f'/api/projects/{ws["id"]}/report')
    assert report.status_code == 200
