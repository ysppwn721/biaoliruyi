"""从巨潮资讯网批量下载年度报告，构建中文「文档 + 表格」训练语料。

为什么选年度报告：
  - 文字叙述（管理层讨论与分析）与财务表格天然在同一文档
  - 官方公开披露，无需授权
  - 表格结构规整，且自带「本期数 / 上期数 / 变动比例」——可直接用于构造训练标签

用法：
  python fetch_annual_reports.py --pages 3 --limit 30 --out <目录>
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

QUERY = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
STATIC = 'http://static.cninfo.com.cn/'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'


def post(url, data, timeout=40):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        'User-Agent': UA,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def list_announcements(category, se_date, pages):
    """按板块与日期区间列举年报，返回 (标题, 代码, 下载路径, 大小KB) 列表。"""
    out, seen = [], set()
    for page in range(1, pages + 1):
        try:
            data = post(QUERY, {
                'pageNum': page, 'pageSize': 30, 'column': 'szse', 'tabName': 'fulltext',
                'category': category, 'seDate': se_date,
                'sortName': '', 'sortType': '', 'isHLtitle': 'true',
            })
        except Exception as exc:
            print(f'    [警告] 第 {page} 页查询失败: {exc}')
            continue
        items = data.get('announcements') or []
        if not items:
            break
        for it in items:
            url = it.get('adjunctUrl') or ''
            if not url or url in seen:
                continue
            seen.add(url)
            title = re.sub(r'<[^>]+>', '', it.get('announcementTitle') or '')
            out.append({'title': title, 'code': it.get('secCode') or '',
                        'name': it.get('secName') or '', 'url': url,
                        'size_kb': it.get('adjunctSize') or 0})
        time.sleep(0.4)
    return out


def download(url, dest, timeout=180):
    req = urllib.request.Request(STATIC + url, headers={'User-Agent': UA,
                                                        'Referer': 'http://www.cninfo.com.cn/'})
    tmp = dest.with_suffix('.part')
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open('wb') as fh:
        total = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            fh.write(chunk)
            total += len(chunk)
    tmp.replace(dest)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--pages', type=int, default=3)
    ap.add_argument('--limit', type=int, default=30)
    ap.add_argument('--min-kb', type=int, default=800, help='过小的多为摘要或更正公告，跳过')
    ap.add_argument('--max-kb', type=int, default=12000, help='过大的多为附件合订本，跳过')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'manifest.jsonl'

    # 两个板块交替取，增加行业多样性
    plan = [('category_ndbg_szsh', '2024-01-01~2024-12-31'),   # 深市主板
            ('category_ndbg_szsh', '2024-01-01~2024-12-31')]
    listed = list_announcements(plan[0][0], plan[0][1], args.pages)
    print(f'检索到 {len(listed)} 条公告记录')

    picked = [x for x in listed if args.min_kb <= x['size_kb'] <= args.max_kb][:args.limit]
    print(f'筛选后待下载 {len(picked)} 份（体积 {args.min_kb}—{args.max_kb} KB）')

    ok, fail = 0, 0
    done = set()
    if manifest.exists():
        for line in manifest.open(encoding='utf-8'):
            try:
                done.add(json.loads(line)['url'])
            except Exception:
                pass
        print(f'已有 {len(done)} 份，续传跳过')

    with manifest.open('a', encoding='utf-8') as mf:
        for i, item in enumerate(picked, 1):
            if item['url'] in done:
                continue
            safe = f"{item['code']}_{re.sub(r'[^0-9A-Za-z一-龥]', '', item['title'])[:40]}"
            dest = out / f'{safe}.pdf'
            if dest.exists() and dest.stat().st_size > 10000:
                continue
            try:
                size = download(item['url'], dest)
                rec = {**item, 'file': dest.name, 'bytes': size}
                mf.write(json.dumps(rec, ensure_ascii=False) + '\n')
                mf.flush()
                ok += 1
                print(f"  [{i}/{len(picked)}] {dest.name}  {size/1024/1024:.2f} MB")
            except Exception as exc:
                fail += 1
                print(f"  [{i}/{len(picked)}] 失败 {item['code']}: {exc}")
            time.sleep(0.6)

    print(f'\n完成：成功 {ok}，失败 {fail}，目录 {out}')
    total = sum(f.stat().st_size for f in out.glob('*.pdf'))
    print(f'语料总量：{len(list(out.glob("*.pdf")))} 份 PDF，{total/1024/1024:.1f} MB')


if __name__ == '__main__':
    main()
