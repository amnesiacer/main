#!/usr/bin/env python3
"""
从 dashboard_data.json 生成 dashboard.html
用法: python3 generate_html.py

数据更新流程:
  1. 编辑 dashboard_data.json（更新项目/收益/拖欠/分配数据）
  2. 运行 python3 generate_html.py
  3. 推送: git add -A && git commit -m "数据更新" && git push amnesiacer main
"""
import json, os, html as h

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, 'dashboard_data.json')
HTML_PATH = os.path.join(BASE, 'dashboard.html')

with open(DATA_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

s = data.get("summary", {})
css = data.get("css", "")

# ── Render table rows ──
def render_rows(rows, has_arrear=False, expand_groups=None):
    if expand_groups is None:
        expand_groups = set()
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
            cell_content = h.escape(c)
            # Add expand button to first cell of grouped project rows
            if ci == 1 and r.get("group") in expand_groups:
                cell_content = (
                    f'<span class="proj-name proj-name-link" '
                    f'onclick="viewProjectIncome(\'{h.escape(c)}\')">{h.escape(c)}</span>'
                    f'<button class="expand-btn" onclick="toggleGroup(this)">▶ 展开明细</button>'
                )
            cells_html += f"<td{cc}>{cell_content}</td>"
        out.append(f"        <tr{attrs}>{cells_html}</tr>")
    return "\n".join(out)

# ── Filter options ──
def render_options(filters, key):
    opts = filters.get(key, [])
    return "\n".join(
        f'<option value="{h.escape(o["value"])}">{h.escape(o["label"])}</option>' for o in opts
    )

# ── Data ──
# Find groups that have sub-rows (for expand buttons)
expand_groups = set()
for r in data["projects"]:
    if r.get("parent"):
        expand_groups.add(r["parent"])

proj_rows = render_rows(data["projects"], expand_groups=expand_groups)
income_rows = render_rows(data["income"], has_arrear=True)
arrears_rows = render_rows(data["arrears"])
dist_rows = render_rows(data["distribution"])

proj_opts = render_options(data.get("filters",{}), "filter-projects")
income_opts = render_options(data.get("filters",{}), "filter-income")
arrears_opts = render_options(data.get("filters",{}), "filter-arrears")
dist_opts = render_options(data.get("filters",{}), "filter-dist")

proj_headers = ["项目名称", "所属村", "运营主体", "合同期限", "约定年收益(万)", "应缴合计(万)", "实缴合计(万)", "拖欠合计(万)"]
income_headers = ["项目名称", "收益周期", "实缴时间", "实缴金额(元)", "实缴状态"]
arrears_headers = ["项目名称", "收益周期", "合作方", "合同周期", "应缴(万元)", "实缴(万元)", "已分配(万元)", "拖欠(万元)"]
dist_headers = ["项目名称", "收益周期", "姓名", "身份证", "分配金额(元)", "银行卡号", "分配日期", "备注"]

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
    <div class="tab" onclick="switchTab('income',this)">💰 收益台账</div>
    <div class="tab" onclick="switchTab('arrears',this)">⚠️ 拖欠明细</div>
    <div class="tab" onclick="switchTab('distribution',this)">📤 分配明细</div>
  </div>

  <!-- 项目总览 -->
  <div id="panel-projects" class="panel active">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-projects" onchange="filterRows('tbody-projects','filter-projects')">
{proj_opts}
      </select>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>{"".join(f"<th>{th}</th>" for th in proj_headers)}</tr></thead>
      <tbody id="tbody-projects">
{proj_rows}
      </tbody>
    </table></div>
  </div>

  <!-- 收益台账 -->
  <div id="panel-income" class="panel">
    <div class="filter-bar">
      <label>筛选项目：</label>
      <select id="filter-income" onchange="filterRows('tbody-income','filter-income')">
{income_opts}
      </select>
    </div>
    <div class="tbl-wrap"><table>
      <thead><tr>{"".join(f"<th>{th}</th>" for th in income_headers)}</tr></thead>
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
      <thead><tr>{"".join(f"<th>{th}</th>" for th in arrears_headers)}</tr></thead>
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
      <thead><tr>{"".join(f"<th>{th}</th>" for th in dist_headers)}</tr></thead>
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
function viewProjectIncome(projectName) {{
  const sel = document.getElementById('filter-income');
  if (sel) {{
    for (let o of sel.options) {{
      if (o.value && projectName.includes(o.value)) {{ sel.value = o.value; break; }}
    }}
    filterRows('tbody-income', 'filter-income');
  }}
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab')[1].classList.add('active');
  document.getElementById('panel-income').classList.add('active');
}}
</script>
</body>
</html>'''

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html_out)

print(f"✅ dashboard.html 已生成 ({len(html_out)} 字符)")
print(f"   项目总览: {len(data['projects'])} 行")
print(f"   收益台账: {len(data['income'])} 行")
print(f"   拖欠明细: {len(data['arrears'])} 行")
print(f"   分配明细: {len(data['distribution'])} 行")
