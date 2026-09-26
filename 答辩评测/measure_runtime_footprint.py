"""实测演示服务的资源占用，用于确定云主机规格。

分三阶段采样当前进程 RSS：
  1. 仅导入 Web 框架与应用（空载）
  2. 载入本地 ONNX 重排模型后（BGE-reranker-v2-m3 INT8）
  3. 跑一次真实批推理后；另外测一遍完整导入闭环的峰值
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('ZHILIAN_LOCAL_RERANKER_ENABLED', '1')

PROC = psutil.Process()
READINGS: list[tuple[str, float, float]] = []


def mark(label: str) -> None:
    info = PROC.memory_info()
    cpu = PROC.cpu_times()
    READINGS.append((label, info.rss / 1024 / 1024, (cpu.user + cpu.system)))
    print(f"{label:<34} RSS {info.rss/1024/1024:8.1f} MB   CPU累计 {cpu.user+cpu.system:7.2f}s")


def main() -> None:
    mark('0 起始')

    from zhilian.app import create_app            # noqa: F401
    mark('1 导入 FastAPI 应用')

    from zhilian import office, engine
    facts = office.read_facts(str(ROOT / '长文Word测试' / '配套数据_初始.xlsx'), 'f')
    mark('2 读取事实表')

    from zhilian import reranker
    print('     reranker status:', reranker.status()['enabled'])
    scores = reranker.score_pairs('本期销售额为125万元', facts, batch_size=8)
    mark('3 载入 ONNX 模型并推理 6 对')

    # 批量压力：模拟一次把一批困难论断交给本地模型
    claims = ['本期销售额为125万元', '本期销售收入为125万元', '公司本期实现营收125万元',
              'A产品销售量为80件', '本期费用为80万元', '报告期销售额突破120万元'] * 12
    started = time.perf_counter()
    total = 0
    for text in claims:
        total += len(reranker.score_pairs(text, facts, batch_size=8))
    elapsed = time.perf_counter() - started
    mark(f'4 连续 {len(claims)} 次推理（{elapsed:.1f}s，{total} 对）')

    # 完整闭环峰值：建项目 -> 扫描 -> 抽取
    import tempfile
    from zhilian.demo import create_demo
    from zhilian.store import Store
    tmp = Path(tempfile.mkdtemp())
    store = Store(tmp / 'data')
    paths = create_demo(tmp / 'files')
    ws = store.create('容量实测', paths)
    mark(f'5 完整导入闭环（{len(ws["claims"])} 条论断）')

    peak = PROC.memory_info().rss
    print()
    print(f'最终 RSS：{peak/1024/1024:.1f} MB')
    print(f'峰值 RSS：{max(r[1] for r in READINGS):.1f} MB')
    print(f'纯 CPU 累计：{READINGS[-1][2]:.2f}s')


if __name__ == '__main__':
    main()
