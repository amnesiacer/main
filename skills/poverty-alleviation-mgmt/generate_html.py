#!/usr/bin/env python3
"""
从 dashboard_data.json 生成 dashboard.html
用法: python3 generate_html.py

数据更新流程:
  1. 编辑 dashboard_data.json（更新项目/收益/拖欠/分配数据）
  2. 运行 python3 generate_html.py
  3. 推送: git add -A && git commit -m "数据更新" && git push amnesiacer main
"""
import json, os, html as h, re

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, 'dashboard_data.json')
HTML_PATH = os.path.join(BASE, 'dashboard.html')

with open(DATA_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

s = data.get("summary", {})
css = data.get("css", "")

# ── Render table rows ──
def render_rows(rows, has_arrear=False):
    out = []
    for r in rows:
        cls = r.get("class", "")
        attrs = f' class="{cls}"' if cls else ""
        if r.get("group"): attrs += f' data-group="{r["group"]}"'
        if r.get("parent"): attrs += f' data-parent="{r["parent"]}"'
        if r.get("project"): attrs += f' data-project="{r["project"]}"'
        ccs = r.get("cell_classes", [])
        ci, cells_html = 0, ""
        for c in r["cells"]:
            cc = ""
            if has_arrear and ci < len(ccs) and ccs[ci]:
                cc = f' class="{ccs[ci]}"'
            ci += 1
            cells_html += f"<td{cc}>{h.escape(c)}</td>"
        out.append(f"        <tr{attrs}>{cells_html}</tr>")
    return "\n".join(out)

# ── Render project cards ──
def render_project_cards(rows):
    cards = []
    i = 0
    while i < len(rows):
        r = rows[i]
        cls = r.get("class", "")
        if "proj-main-row" in cls:
            gid = r.get("group", "")
            subs = []
            i += 1
            while i < len(rows) and rows[i].get("parent") == gid:
                subs.append(rows[i])
                i += 1
            cards.append(("main", r, subs))
        elif "note-row" in cls:
            cards.append(("note", r, []))
            i += 1
        else:
            i += 1
    return cards

def build_cards_html(cards):
    out = []
    for ctype, r, subs in cards:
        if ctype == "note":
            # Summary row
            cells = r["cells"]
            out.append(f'      <div class="note-row">{" | ".join(h.escape(c) for c in cells)}</div>')
            continue
        cells = r["cells"]
        name = cells[0]
        villages = cells[1]
        partner = cells[2]
        period = cells[3]
        should_pay = cells[4]
        paid = cells[5]
        distributed = cells[6]
        arrear = cells[7]
        gid = r.get("group", "")
        has_arrear = float(arrear) > 0
        arrear_class = " arrear-yes" if has_arrear else ""
        arrear_lbl = f'<span class="arrear-badge">拖欠</span>' if has_arrear else ""
        expand_btn = ""
        subs_html = ""
        if subs:
            expand_btn = f'<button class="expand-btn" onclick="toggleCardGroup(this)">▶ 展开明细</button>'
            sub_items = []
            for sr in subs:
                sc = sr["cells"]
                s_arrear = float(sc[7]) > 0
                s_cls = " arrear-yes" if s_arrear else ""
                sub_items.append(
                    f'        <div class="proj-sub-item">\n'
                    f'          <div class="sub-name">{h.escape(sc[0].replace("↳ ",""))}</div>\n'
                    f'          <div class="sub-metrics">\n'
                    f'            <span>应缴 <b>{h.escape(sc[4])}</b></span>\n'
                    f'            <span>实缴 <b>{h.escape(sc[5])}</b></span>\n'
                    f'            <span>已分配 <b>{h.escape(sc[6])}</b></span>\n'
                    f'            <span class="{s_cls}">拖欠 <b>{h.escape(sc[7])}</b></span>\n'
                    f'          </div>\n'
                    f'        </div>')
            subs_html = f'\n      <div class="proj-subs hidden" data-parent="{h.escape(gid)}">\n' + "\n".join(sub_items) + '\n      </div>'
        onclick = f"onclick=\"viewProjectIncome('{h.escape(name)}')\""
        out.append(
            f'      <div class="proj-card" data-group="{h.escape(gid)}">\n'
            f'        <h3><span class="proj-name-link" {onclick}>{h.escape(name)}</span>{arrear_lbl}{expand_btn}</h3>\n'
            f'        <div class="detail">\n'
            f'          <div>🏘️ {h.escape(villages)}</div>\n'
            f'          <div>🤝 {h.escape(partner)}</div>\n'
            f'          <div>📅 {h.escape(period)}</div>\n'
            f'        </div>\n'
            f'        <div class="metrics">\n'
            f'          <div><span class="m-label">应缴</span><span class="m-value">{h.escape(should_pay)}</span></div>\n'
            f'          <div><span class="m-label">实缴</span><span class="m-value">{h.escape(paid)}</span></div>\n'
            f'          <div><span class="m-label">已分配</span><span class="m-value">{h.escape(distributed)}</span></div>\n'
            f'          <div{arrear_class}><span class="m-label">拖欠</span><span class="m-value">{h.escape(arrear)}</span></div>\n'
            f'        </div>{subs_html}\n'
            f'      </div>')
    return "\n".join(out)

# ── Filter options ──
def render_options(filters, key):
    opts = filters.get(key, [])
    return "\n".join(
        f'<option value="{h.escape(o["value"])}">{h.escape(o["label"])}"</option>' for o in opts
    )

# ── Data ──
income_rows = render_rows(data["income"], has_arrear=True)
arrears_rows = render_rows(data["arrears"])
dist_rows = render_rows(data["distribution"])

income_opts = render_options(data.get("filters",{}), "filter-income")
arrears_opts = render_options(data.get("filters",{}), "filter-arrears")
dist_opts = render_options(data.get("filters",{}), "filter-dist")

cards = render_project_cards(data["projects"])
cards_html = build_cards_html(cards)

income_headers = ["项目名称", "收益周期", "实缴时间", "实缴金额(元)", "实缴状态"]
arrears_headers = ["项目名称", "收益周期", "合作方", "合同周期", "应缴(万元)", "实缴(万元)", "已分配(万元)", "拖欠(万元)"]
dist_headers = ["项目名称", "收益周期", "姓名", "身份证", "分配金额(元)", "银行卡号", "分配日期", "备注"]

# ── Build CSS with card styles ──
# Ensure proj-card styles exist
if '.proj-card' not in css:
    css += """
  /* ── Project Cards ── */
  .proj-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
  .proj-card { background: var(--card); border-radius: var(--radius-sm); padding: 14px 16px;
    box-shadow: var(--shadow); transition: all .2s; border-left: 4px solid var(--pri); cursor: default; }
  .proj-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
  .proj-card h3 { font-size: .9rem; color: var(--ink); margin: 0 0 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .proj-card .detail { font-size: .78rem; color: var(--ink2); line-height: 1.8; margin-bottom: 10px; }
  .proj-card .detail div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .proj-card .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; font-size: .78rem; }
  .proj-card .metrics > div { text-align: center; padding: 6px 4px; background: var(--bg); border-radius: 6px; }
  .proj-card .m-label { display: block; color: var(--ink2); font-size: .7rem; margin-bottom: 2px; }
  .proj-card .m-value { display: block; font-weight: 700; color: var(--ink); font-size: .85rem; }
  .proj-card .arrear-yes .m-value { color: #e74c3c; }
  .proj-card .arrear-yes .m-label { color: #e74c3c; }
  .arrear-badge { background: #e74c3c; color: #fff; font-size: .65rem; padding: 1px 6px; border-radius: 8px; }
  .proj-name-link { cursor: pointer; color: var(--pri); text-decoration: underline; text-underline-offset: 2px; }
  .proj-name-link:hover { color: var(--pri2); }
  .proj-card .expand-btn { margin-left: auto; background: none; border: 1px solid var(--pri); color: var(--pri);
    font-size: .72rem; padding: 2px 8px; border-radius: 8px; cursor: pointer; white-space: nowrap; }
  .proj-card .expand-btn:hover { background: var(--pri); color: #fff; }
  .proj-subs { margin-top: 10px; border-top: 1px dashed var(--border); padding-top: 8px; }
  .proj-sub-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0;
    font-size: .78rem; border-bottom: 1px solid var(--bg); }
  .proj-sub-item:last-child { border-bottom: none; }
  .proj-sub-item .sub-name { color: var(--ink2); flex: 1; }
  .proj-sub-item .sub-metrics { display: flex; gap: 10px; }
  .proj-sub-item .sub-metrics span { white-space: nowrap; }
  .proj-sub-item .sub-metrics .arrear-yes { color: #e74c3c; }
  .note-row { text-align: center; color: var(--ink2); font-size: .82rem; padding: 12px; }
  .back-btn { background: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 6px 14px; cursor: pointer; font-size: .82rem; color: var(--ink); transition: all .2s; }
  .back-btn:hover { background: var(--pri); color: #fff; border-color: var(--pri); }
"""

html_out = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>马店镇帮扶项目收益管理看板</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>

<div class="wrap">
  <div class="header">
    <h1>马店镇帮扶项目收益管理看板</h1>
    <p class="subtitle">洛阳市洛宁县马店镇 · 数据更新日期: 2026-03-27</p>
  </div>

  <div class="stats-row">
    <div class="stat"><div class="num">{s.get("项目总数","")}</div><div class="lbl">项目总数</div></div>
    <div class="stat"><div class="num">{s.get("累计实缴","")}</div><div class="lbl">累计实缴（万元）</div></div>
    <div class="stat"><div class="num">{s.get("当前拖欠","")}</div><div class="lbl">当前拖欠（万元）</div></div>
    <div class="stat"><div class="num">{s.get("拖欠项目数","")}</div><div class="lbl">拖欠项目数</div></div>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('projects',this)">📋 项目总览</div>
    <div class="tab" onclick="switchTab('arrears',this)">⚠️ 拖欠明细</div>
    <div class="tab" onclick="switchTab('distribution',this)">📤 分配明细</div>
  </div>

  <!-- 项目总览 -->
  <div id="panel-projects" class="panel active">
    <div class="proj-grid">
{cards_html}
    </div>
  </div>

  <!-- 收益台账 -->
  <div id="panel-income" class="panel">
    <div class="filter-bar">
      <button class="back-btn" onclick="backToProjects()">← 返回项目总览</button>
      <label>筛选项目：</label>
      <select id="filter-income" onchange="filterRows('tbody-income','filter-income')">
{income_opts}
      </select>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>{"".join(f"<th>{h}</th>" for h in income_headers)}</tr></thead>
      <tbody id="tbody-income">
{income_rows}
      </tbody>
    </table></div>
  </div>

  <!-- 拖欠明细 -->
  <div id="panel-arrears" class="panel">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-arrears" onchange="filterRows('tbody-arrears','filter-arrears')">
{arrears_opts}
      </select>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>{"".join(f"<th>{h}</th>" for h in arrears_headers)}</tr></thead>
      <tbody id="tbody-arrears">
{arrears_rows}
      </tbody>
    </table></div>
  </div>

  <!-- 分配明细 -->
  <div id="panel-distribution" class="panel">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-dist" onchange="filterRows('tbody-dist','filter-dist')">
{dist_opts}
      </select>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>{"".join(f"<th>{h}</th>" for h in dist_headers)}</tr></thead>
      <tbody id="tbody-dist">
{dist_rows}
      </tbody>
    </table></div>
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
    tr.style.display = (!val || names.includes(tr.dataset.project)) ? '' : 'none';
  }});
}}
function toggleGroup(btn) {{
  const row = btn.closest('tr');
  const gid = row.dataset.group;
  const subs = document.querySelectorAll('tr[data-parent="' + gid + '"]');
  const open = btn.textContent.startsWith('▼');
  subs.forEach(r => r.classList.toggle('hidden', open));
  btn.textContent = open ? '▶ 展开明细' : '▼ 收起明细';
}}
function toggleCardGroup(btn) {{
  const card = btn.closest('.proj-card');
  const gid = card.dataset.group;
  const subs = card.querySelector('.proj-subs[data-parent="' + gid + '"]');
  if (!subs) return;
  const open = !subs.classList.contains('hidden');
  subs.classList.toggle('hidden', open);
  btn.textContent = open ? '▶ 展开明细' : '▼ 收起明细';
}}
function viewProjectIncome(projectName) {{
  const sel = document.getElementById('filter-income');
  if (sel) {{
    let found = false;
    for (let o of sel.options) {{
      if (o.value === projectName) {{ sel.value = o.value; found = true; break; }}
    }}
    if (!found) {{
      for (let o of sel.options) {{
        if (o.value && projectName.includes(o.value)) {{ sel.value = o.value; break; }}
      }}
    }}
    filterRows('tbody-income', 'filter-income');
  }}
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-income').classList.add('active');
}}
function backToProjects() {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelector('.tab').classList.add('active');
  document.getElementById('panel-projects').classList.add('active');
}}
</script>
</body>
</html>'''

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html_out)

print(f"✅ dashboard.html 已生成 ({len(html_out)} 字符)")
print(f"   项目卡片: {len([c for c in cards if c[0]=='main'])} 个")
print(f"   收益台账: {len(data['income'])} 行")
print(f"   拖欠明细: {len(data['arrears'])} 行")
print(f"   分配明细: {len(data['distribution'])} 行")
