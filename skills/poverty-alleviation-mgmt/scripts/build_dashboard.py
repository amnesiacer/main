#!/usr/bin/env python3
"""
帮扶项目收益管理看板生成器
- 从数据库读取所有数据
- 生成美观响应式 HTML 看板
- 推送到 GitHub amnesiacer/main 仓库（index.html）
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime

# ── GitHub 配置 ──────────────────────────────────────────────────────────────
GITHUB_REPO   = "amnesiacer/main"
GITHUB_BRANCH = "main"
GITHUB_FILE   = "index.html"
# Token 从环境变量读取：export GITHUB_TOKEN=ghp_xxx
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")


def _ok(data, message=""):
    print(json.dumps({"status": "ok", "message": message, "data": data},
                     ensure_ascii=False, default=str))
    sys.exit(0)

def _fail(msg):
    print(json.dumps({"status": "error", "message": msg, "data": None},
                     ensure_ascii=False))
    sys.exit(1)


# ── 数据库读取 ────────────────────────────────────────────────────────────────
def fetch_data():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db import get_conn, get_cursor

    conn = get_conn()
    cur  = get_cursor(conn)
    today_str = str(date.today())
    try:
        # 项目列表
        cur.execute("""
            SELECT p.*,
                   COALESCE(SUM(CASE WHEN r.period_end::date <= %s::date THEN r.due_amount    ELSE 0 END),0) AS total_due,
                   COALESCE(SUM(r.paid_amount),0) AS total_paid,
                   COALESCE(SUM(CASE WHEN r.period_end::date <= %s::date THEN r.arrear_amount ELSE 0 END),0) AS total_arrear,
                   COUNT(r.id) AS period_count
            FROM pam_projects p
            LEFT JOIN pam_income_records r ON r.project_id = p.id
            GROUP BY p.id
            ORDER BY p.name
        """, (today_str, today_str))
        projects = [dict(r) for r in cur.fetchall()]

        # 收益台账（仅已到期）
        cur.execute("""
            SELECT r.*, p.name AS proj_name
            FROM pam_income_records r
            JOIN pam_projects p ON p.id = r.project_id
            WHERE r.period_end::date <= %s::date
            ORDER BY p.name, r.period_start
        """, (today_str,))
        income_records = [dict(r) for r in cur.fetchall()]

        # 拖欠明细
        cur.execute("""
            SELECT r.project_name, r.period_label, r.period_start, r.period_end,
                   r.due_amount, r.paid_amount, r.arrear_amount
            FROM pam_income_records r
            WHERE r.arrear_amount > 0 AND r.period_end::date <= %s::date
            ORDER BY r.project_name, r.period_start
        """, (today_str,))
        arrears = [dict(r) for r in cur.fetchall()]

        # 分配明细
        cur.execute("""
            SELECT d.name, d.id_card, d.amount, d.bank_card, d.remark,
                   r.project_name, r.period_label, r.distributed_at
            FROM pam_distribution_details d
            JOIN pam_income_records r ON r.id = d.income_record_id
            ORDER BY r.project_name, r.period_start, d.id
        """)
        distributions = [dict(r) for r in cur.fetchall()]

        return {
            "projects": projects,
            "income_records": income_records,
            "arrears": arrears,
            "distributions": distributions,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    finally:
        cur.close()
        conn.close()


# ── HTML 看板生成 ─────────────────────────────────────────────────────────────
def build_html(data):
    """生成完整响应式看板 HTML"""

    def fmt_money(v):
        try:
            return "{:.4f}".format(float(v))
        except Exception:
            return str(v)

    def mask_id(s):
        s = str(s)
        if len(s) >= 8:
            return s[:4] + "**********" + s[-4:]
        return s

    # ── 项目合并逻辑：提取"基础名称"（去掉村名后缀差异）
    # 简单策略：若多个项目名称只有村名不同，归为同一组
    # 通过：去掉名称中第一个"村"字及之前内容，剩余相同则合并
    # 更稳健：找到最长公共前缀
    def get_group_key(name):
        # 去掉所有"XX村"前缀/后缀后的核心名称
        import re
        # 匹配 "X村X村" 等开头的村名前缀
        cleaned = re.sub(r'^[\u4e00-\u9fa5]{1,4}村', '', name)
        if cleaned != name:
            return cleaned.strip()
        return name

    from itertools import groupby
    import re

    projects = data["projects"]

    # 构建项目组
    groups = {}
    for p in projects:
        key = get_group_key(p["name"])
        if key not in groups:
            groups[key] = []
        groups[key].append(p)

    # 构建项目组 HTML 行
    project_rows_html = ""
    merged_project_names = {}  # name -> group_key，用于下拉筛选

    for gkey, gprojs in groups.items():
        merged_project_names[gkey] = [p["name"] for p in gprojs]
        is_merged = len(gprojs) > 1
        total_due    = sum(float(p.get("total_due", 0))    for p in gprojs)
        total_paid   = sum(float(p.get("total_paid", 0))   for p in gprojs)
        total_arrear = sum(float(p.get("total_arrear", 0)) for p in gprojs)

        # 主行
        main_villages = "、".join(v for p in gprojs for v in (p.get("villages") or []))
        first = gprojs[0]
        arrear_class = "arrear-yes" if total_arrear > 0 else "arrear-no"
        expand_btn = (
            '<button class="expand-btn" onclick="toggleGroup(this)">▶ 展开明细</button>'
            if is_merged else ""
        )
        group_id = "grp-" + re.sub(r'[^\w]', '_', gkey)

        project_rows_html += f"""
        <tr class="proj-main-row" data-group="{group_id}">
          <td><span class="proj-name">{gkey}</span>{expand_btn}</td>
          <td>{main_villages or "-"}</td>
          <td>{first.get("operator") or "-"}</td>
          <td>{str(first.get("contract_start",""))[:10]} ~ {str(first.get("contract_end",""))[:10]}</td>
          <td>{fmt_money(sum(float(p.get("agreed_income",0)) for p in gprojs))}</td>
          <td>{fmt_money(total_due)}</td>
          <td>{fmt_money(total_paid)}</td>
          <td class="{arrear_class}">{fmt_money(total_arrear)}</td>
        </tr>"""

        # 子行（合并时展示各村明细）
        if is_merged:
            for sp in gprojs:
                s_arrear = float(sp.get("total_arrear", 0))
                s_class = "arrear-yes" if s_arrear > 0 else "arrear-no"
                s_villages = "、".join(sp.get("villages") or [])
                project_rows_html += f"""
        <tr class="proj-sub-row hidden" data-parent="{group_id}">
          <td class="sub-indent">↳ {sp["name"]}</td>
          <td>{s_villages or "-"}</td>
          <td>{sp.get("operator") or "-"}</td>
          <td>{str(sp.get("contract_start",""))[:10]} ~ {str(sp.get("contract_end",""))[:10]}</td>
          <td>{fmt_money(sp.get("agreed_income",0))}</td>
          <td>{fmt_money(sp.get("total_due",0))}</td>
          <td>{fmt_money(sp.get("total_paid",0))}</td>
          <td class="{s_class}">{fmt_money(s_arrear)}</td>
        </tr>"""

    # ── 收益台账筛选选项（合并后的组名）
    income_filter_opts = '<option value="">全部项目</option>'
    for gkey, names in merged_project_names.items():
        income_filter_opts += f'<option value="{"|".join(names)}">{gkey}</option>'

    # 收益台账行
    income_rows_html = ""
    for r in data["income_records"]:
        arrear = float(r.get("arrear_amount", 0))
        dist_status = "已分配" if r.get("is_distributed") else "未分配"
        dist_class = "dist-yes" if r.get("is_distributed") else "dist-no"
        arrear_class = "arrear-yes" if arrear > 0 else ""
        income_rows_html += f"""
        <tr data-project="{r['proj_name']}">
          <td>{r['proj_name']}</td>
          <td>{r['period_label']}</td>
          <td>{fmt_money(r['due_amount'])}</td>
          <td>{fmt_money(r['paid_amount'])}</td>
          <td class="{arrear_class}">{fmt_money(arrear)}</td>
          <td class="{dist_class}">{dist_status}</td>
          <td>{str(r.get("distributed_at","") or "")[:10] or "-"}</td>
          <td>{fmt_money(r.get("distributed_amount",0))}</td>
        </tr>"""

    # ── 拖欠明细行
    arrear_filter_opts = '<option value="">全部项目</option>'
    arrear_proj_names = sorted(set(r["project_name"] for r in data["arrears"]))
    arrear_groups_seen = set()
    for pname in arrear_proj_names:
        gkey = get_group_key(pname)
        if gkey not in arrear_groups_seen:
            arrear_groups_seen.add(gkey)
            names_in_group = merged_project_names.get(gkey, [pname])
            arrear_filter_opts += f'<option value="{"|".join(names_in_group)}">{gkey}</option>'

    arrear_rows_html = ""
    for r in data["arrears"]:
        arrear_rows_html += f"""
        <tr data-project="{r['project_name']}">
          <td>{r['project_name']}</td>
          <td>{r['period_label']}</td>
          <td>{fmt_money(r['due_amount'])}</td>
          <td>{fmt_money(r['paid_amount'])}</td>
          <td class="arrear-yes">{fmt_money(r['arrear_amount'])}</td>
        </tr>"""

    # ── 分配明细行
    dist_filter_opts = '<option value="">全部项目</option>'
    dist_proj_names = sorted(set(r["project_name"] for r in data["distributions"]))
    dist_groups_seen = set()
    for pname in dist_proj_names:
        gkey = get_group_key(pname)
        if gkey not in dist_groups_seen:
            dist_groups_seen.add(gkey)
            names_in_group = merged_project_names.get(gkey, [pname])
            dist_filter_opts += f'<option value="{"|".join(names_in_group)}">{gkey}</option>'

    dist_rows_html = ""
    for r in data["distributions"]:
        dist_rows_html += f"""
        <tr data-project="{r['project_name']}">
          <td>{r['project_name']}</td>
          <td>{r['period_label']}</td>
          <td>{r['name']}</td>
          <td>{mask_id(r['id_card'])}</td>
          <td>{fmt_money(r['amount'])}</td>
          <td>{r['bank_card']}</td>
          <td>{str(r.get("distributed_at","") or "")[:10] or "-"}</td>
          <td>{r.get("remark","") or "-"}</td>
        </tr>"""

    # ── 汇总数字
    total_projects = len(groups)
    total_arrear_all = sum(float(r["arrear_amount"]) for r in data["arrears"])
    total_paid_all = sum(float(p.get("total_paid", 0)) for p in projects)
    arrear_count = len(set(r["project_name"] for r in data["arrears"]))

    generated_at = data["generated_at"]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>帮扶项目收益管理看板</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink:       #1a1a2e;
    --ink-2:     #2d2d44;
    --ink-light: #6b6b85;
    --gold:      #c9962a;
    --gold-pale: #f5e9c8;
    --red:       #c0392b;
    --red-pale:  #fdecea;
    --green:     #1a7c4e;
    --green-pale:#e8f5ee;
    --blue:      #2258a5;
    --blue-pale: #e8eef8;
    --bg:        #faf8f4;
    --card:      #ffffff;
    --border:    #e2ddd5;
    --radius:    10px;
    --shadow:    0 2px 16px rgba(0,0,0,.07);
    --mono:      'JetBrains Mono', monospace;
    --serif:     'Noto Serif SC', serif;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); font-family: var(--serif); color: var(--ink); min-height: 100vh; }}

  /* ── 顶部 Banner ── */
  .banner {{
    background: linear-gradient(135deg, var(--ink) 0%, var(--ink-2) 100%);
    padding: 28px 24px 22px;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 10px;
  }}
  .banner-title {{ color: #fff; font-size: clamp(1.1rem, 3.5vw, 1.6rem); font-weight: 700; letter-spacing: .04em; }}
  .banner-title span {{ color: var(--gold); }}
  .banner-sub {{ color: rgba(255,255,255,.5); font-size: .78rem; font-family: var(--mono); }}

  /* ── 汇总卡片 ── */
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; padding: 20px 20px 0; }}
  .stat-card {{
    background: var(--card); border-radius: var(--radius);
    padding: 18px 16px; box-shadow: var(--shadow);
    border-left: 4px solid var(--gold);
  }}
  .stat-card.red  {{ border-left-color: var(--red); }}
  .stat-card.green{{ border-left-color: var(--green); }}
  .stat-card.blue {{ border-left-color: var(--blue); }}
  .stat-label {{ font-size: .72rem; color: var(--ink-light); letter-spacing: .06em; text-transform: uppercase; }}
  .stat-value {{ font-size: clamp(1.3rem, 3vw, 1.8rem); font-weight: 700; margin-top: 4px; font-family: var(--mono); }}
  .stat-card.red  .stat-value {{ color: var(--red); }}
  .stat-card.green .stat-value {{ color: var(--green); }}
  .stat-card.blue  .stat-value {{ color: var(--blue); }}

  /* ── 标签页 ── */
  .tabs {{ display: flex; gap: 0; padding: 20px 20px 0; flex-wrap: wrap; }}
  .tab {{
    padding: 9px 18px; cursor: pointer; font-family: var(--serif);
    font-size: .88rem; font-weight: 600; border: 1.5px solid var(--border);
    background: var(--card); color: var(--ink-light);
    border-bottom: none; border-radius: var(--radius) var(--radius) 0 0;
    margin-right: 4px; transition: all .15s;
  }}
  .tab:hover {{ color: var(--ink); background: var(--gold-pale); }}
  .tab.active {{ background: var(--gold); color: #fff; border-color: var(--gold); }}

  /* ── 内容区 ── */
  .tab-panels {{ padding: 0 20px 30px; }}
  .panel {{
    display: none; background: var(--card);
    border-radius: 0 var(--radius) var(--radius) var(--radius);
    box-shadow: var(--shadow); border: 1.5px solid var(--border);
    overflow: hidden;
  }}
  .panel.active {{ display: block; }}

  /* ── 筛选栏 ── */
  .filter-bar {{
    padding: 14px 16px; background: var(--gold-pale);
    border-bottom: 1px solid var(--border);
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  }}
  .filter-bar label {{ font-size: .8rem; color: var(--ink-light); white-space: nowrap; }}
  .filter-bar select, .filter-bar input {{
    padding: 6px 10px; border: 1px solid var(--border);
    border-radius: 6px; font-family: var(--serif); font-size: .85rem;
    background: #fff; color: var(--ink); cursor: pointer;
  }}

  /* ── 表格 ── */
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .83rem; }}
  thead tr {{ background: var(--ink); }}
  thead th {{ padding: 11px 12px; text-align: left; color: rgba(255,255,255,.88); font-weight: 600; white-space: nowrap; letter-spacing: .03em; }}
  tbody tr {{ border-bottom: 1px solid var(--border); transition: background .1s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: var(--gold-pale); }}
  tbody td {{ padding: 10px 12px; vertical-align: middle; }}
  .arrear-yes {{ color: var(--red); font-weight: 600; }}
  .arrear-no  {{ color: var(--green); }}
  .dist-yes {{ color: var(--green); font-weight: 600; }}
  .dist-no  {{ color: var(--ink-light); }}

  /* ── 合并项目展开 ── */
  .expand-btn {{
    display: inline-block; margin-left: 8px; padding: 2px 8px;
    font-size: .72rem; cursor: pointer; border: 1px solid var(--gold);
    border-radius: 4px; background: transparent; color: var(--gold);
    font-family: var(--serif); transition: all .15s;
  }}
  .expand-btn:hover {{ background: var(--gold); color: #fff; }}
  .proj-main-row td:first-child {{ font-weight: 600; }}
  .proj-sub-row td {{ background: var(--blue-pale); font-size: .8rem; }}
  .sub-indent {{ padding-left: 28px !important; color: var(--blue); }}
  .hidden {{ display: none !important; }}

  /* ── 空状态 ── */
  .empty-state {{ padding: 40px; text-align: center; color: var(--ink-light); font-size: .9rem; }}

  /* ── 响应式 ── */
  @media (max-width: 640px) {{
    .banner {{ padding: 18px 14px; }}
    .stats {{ padding: 14px 14px 0; gap: 10px; }}
    .tabs {{ padding: 14px 14px 0; }}
    .tab {{ padding: 7px 12px; font-size: .8rem; }}
    .tab-panels {{ padding: 0 14px 20px; }}
    thead th, tbody td {{ padding: 8px 8px; font-size: .78rem; }}
  }}
</style>
</head>
<body>

<div class="banner">
  <div>
    <div class="banner-title">帮扶项目<span>收益管理</span>看板</div>
    <div class="banner-sub">数据更新时间：{generated_at}</div>
  </div>
</div>

<!-- 汇总卡片 -->
<div class="stats">
  <div class="stat-card blue">
    <div class="stat-label">项目总数</div>
    <div class="stat-value">{total_projects}</div>
  </div>
  <div class="stat-card green">
    <div class="stat-label">累计实缴（万元）</div>
    <div class="stat-value">{fmt_money(total_paid_all)}</div>
  </div>
  <div class="stat-card red">
    <div class="stat-label">当前拖欠（万元）</div>
    <div class="stat-value">{fmt_money(total_arrear_all)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">拖欠项目数</div>
    <div class="stat-value">{arrear_count}</div>
  </div>
</div>

<!-- 标签页 -->
<div class="tabs">
  <div class="tab active" onclick="switchTab('projects',this)">📋 项目总览</div>
  <div class="tab" onclick="switchTab('income',this)">💰 收益台账</div>
  <div class="tab" onclick="switchTab('arrears',this)">⚠️ 拖欠明细</div>
  <div class="tab" onclick="switchTab('distribution',this)">📤 分配明细</div>
</div>

<div class="tab-panels">

  <!-- 项目总览 -->
  <div id="panel-projects" class="panel active">
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>项目名称</th><th>所属村</th><th>运营主体</th>
          <th>合同期限</th><th>约定年收益(万)</th>
          <th>应缴合计(万)</th><th>实缴合计(万)</th><th>拖欠合计(万)</th>
        </tr></thead>
        <tbody id="tbody-projects">
          {project_rows_html if project_rows_html.strip() else '<tr><td colspan="8" class="empty-state">暂无项目数据</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 收益台账 -->
  <div id="panel-income" class="panel">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-income" onchange="filterRows('tbody-income','filter-income')">
        {income_filter_opts}
      </select>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>项目名称</th><th>收益周期</th><th>应缴(万)</th><th>实缴(万)</th>
          <th>拖欠(万)</th><th>分配状态</th><th>分配日期</th><th>到户金额(万)</th>
        </tr></thead>
        <tbody id="tbody-income">
          {income_rows_html if income_rows_html.strip() else '<tr><td colspan="8" class="empty-state">暂无到期收益记录</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 拖欠明细 -->
  <div id="panel-arrears" class="panel">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-arrears" onchange="filterRows('tbody-arrears','filter-arrears')">
        {arrear_filter_opts}
      </select>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>项目名称</th><th>收益周期</th><th>应缴(万)</th><th>实缴(万)</th><th>拖欠(万)</th>
        </tr></thead>
        <tbody id="tbody-arrears">
          {arrear_rows_html if arrear_rows_html.strip() else '<tr><td colspan="5" class="empty-state">✅ 暂无拖欠记录</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 分配明细 -->
  <div id="panel-distribution" class="panel">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-dist" onchange="filterRows('tbody-dist','filter-dist')">
        {dist_filter_opts}
      </select>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>项目名称</th><th>收益周期</th><th>姓名</th><th>身份证</th>
          <th>分配金额(元)</th><th>银行卡号</th><th>分配日期</th><th>备注</th>
        </tr></thead>
        <tbody id="tbody-dist">
          {dist_rows_html if dist_rows_html.strip() else '<tr><td colspan="8" class="empty-state">暂无分配记录</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

</div>

<script>
function switchTab(name, el) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('panel-' + name).classList.add('active');
}}

function filterRows(tbodyId, selectId) {{
  const val = document.getElementById(selectId).value;
  const names = val ? val.split('|') : [];
  document.querySelectorAll('#' + tbodyId + ' tr[data-project]').forEach(tr => {{
    if (!val || names.includes(tr.dataset.project)) {{
      tr.style.display = '';
    }} else {{
      tr.style.display = 'none';
    }}
  }});
}}

function toggleGroup(btn) {{
  const row = btn.closest('tr');
  const groupId = row.dataset.group;
  const subRows = document.querySelectorAll('tr[data-parent="' + groupId + '"]');
  const isOpen = btn.textContent.startsWith('▼');
  subRows.forEach(r => r.classList.toggle('hidden', isOpen));
  btn.textContent = isOpen ? '▶ 展开明细' : '▼ 收起明细';
}}
</script>
</body>
</html>"""
    return html


# ── GitHub 推送 ───────────────────────────────────────────────────────────────
def push_to_github(html_content: str) -> dict:
    """通过 GitHub API 推送 index.html"""
    import urllib.request
    import base64

    if not GITHUB_TOKEN:
        return {"pushed": False, "reason": "未配置 GITHUB_TOKEN 环境变量"}

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        "Authorization": "token " + GITHUB_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "pam-dashboard-bot"
    }

    # 获取当前文件 SHA（更新时需要）
    sha = None
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            existing = json.loads(resp.read())
            sha = existing.get("sha")
    except Exception:
        pass  # 文件不存在时正常

    content_b64 = base64.b64encode(html_content.encode("utf-8")).decode()
    payload = {
        "message": "自动更新看板 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "content": content_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(api_url, data=data, headers=headers, method="PUT")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            url = result.get("content", {}).get("html_url", "")
            return {"pushed": True, "url": url}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"pushed": False, "reason": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"pushed": False, "reason": str(e)}


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    try:
        data = fetch_data()
    except Exception as e:
        _fail("数据库读取失败：" + str(e))

    html = build_html(data)

    # 保存本地文件（pam.py 会自动推送 GitHub）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, "..", "dashboard.html")
    out_path = os.path.normpath(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    _ok({
        "local_file": out_path,
        "stats": {
            "projects": len(data["projects"]),
            "arrears": len(data["arrears"]),
            "distributions": len(data["distributions"]),
        }
    }, "看板已生成")


if __name__ == "__main__":
    main()
