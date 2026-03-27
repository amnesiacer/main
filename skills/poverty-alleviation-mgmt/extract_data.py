#!/usr/bin/env python3
"""
从 dashboard.html 提取数据 → dashboard_data.json
再用模板引擎生成 → dashboard.html
用法:
  python3 extract_data.py          # 从现有HTML提取数据
  python3 generate_html.py         # 从JSON生成HTML
"""
import json, re, sys, os
from html.parser import HTMLParser

BASE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE, 'dashboard.html')
DATA_PATH = os.path.join(BASE, 'dashboard_data.json')

def extract_data():
    """Parse dashboard.html and extract all structured data into JSON."""
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    data = {
        "summary": {},
        "projects": [],       # 项目总览
        "income": [],         # 收益台账
        "arrears": [],        # 拖欠明细
        "distribution": [],   # 分配明细
        "solar": [],          # 光伏看板
    }

    # ── 1. Summary stats ──
    stat_nums = re.findall(r'<div class="num">([^<]+)</div>\s*<div class="lbl">([^<]+)</div>', html)
    for num, lbl in stat_nums:
        key = lbl.replace('（万元）', '').replace('（', '').replace('）', '')
        data["summary"][key] = num.strip()

    # ── Helper: parse table rows from a tbody ──
    def parse_tbody(tbody_id, html_text):
        match = re.search(rf'id="{tbody_id}"(.*?)(?=</tbody>)', html_text, re.DOTALL)
        if not match:
            return []
        tbody_html = match.group(1)
        rows = []
        for tr_match in re.finditer(r'<tr([^>]*)>(.*?)</tr>', tbody_html, re.DOTALL):
            attrs = tr_match.group(1)
            tr_html = tr_match.group(2)
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr_html, re.DOTALL)
            row = {"cells": [re.sub(r'<[^>]+>', '', c).strip() for c in cells]}
            # Extract data attributes
            cls_m = re.search(r'class="([^"]*)"', attrs)
            grp_m = re.search(r'data-group="([^"]*)"', attrs)
            par_m = re.search(r'data-parent="([^"]*)"', attrs)
            prj_m = re.search(r'data-project="([^"]*)"', attrs)
            if cls_m:
                row["class"] = cls_m.group(1)
            if grp_m:
                row["group"] = grp_m.group(1)
            if par_m:
                row["parent"] = par_m.group(1)
            if prj_m:
                row["project"] = prj_m.group(1)
            # Check for arrear classes on specific cells
            cell_classes = re.findall(r'<td[^>]*class="([^"]*)"[^>]*>', tr_html)
            if cell_classes:
                row["cell_classes"] = cell_classes
            rows.append(row)
        return rows

    # ── 2. Projects ──
    data["projects"] = parse_tbody("tbody-projects", html)

    # ── 3. Income ──
    data["income"] = parse_tbody("tbody-income", html)

    # ── 4. Arrears ──
    data["arrears"] = parse_tbody("tbody-arrears", html)

    # ── 5. Distribution ──
    data["distribution"] = parse_tbody("tbody-dist", html)

    # ── 6. Solar (光伏看板 - cards, not table) ──
    solar_section = re.search(r'id="panel-solar"(.*?)</div>\s*</div>\s*<script', html, re.DOTALL)
    if solar_section:
        solar_html = solar_section.group(1)
        cards = re.findall(r'class="solar-card"(.*?)(?=class="solar-card"|$)', solar_html, re.DOTALL)
        for card in cards:
            title = re.search(r'<div class="s-title">(.*?)</div>', card)
            detail = re.search(r'<div class="detail">(.*?)</div>', card, re.DOTALL)
            if title:
                item = {"title": re.sub(r'<[^>]+>', '', title.group(1)).strip()}
                if detail:
                    lines = [l.strip() for l in re.sub(r'<[^>]+>', '\n', detail.group(1)).split('\n') if l.strip()]
                    item["details"] = lines
                data["solar"].append(item)

    # ── 7. Filter options ──
    filter_options = {}
    for sel_match in re.finditer(r'<select id="(filter-[^"]+)"[^>]*>(.*?)</select>', html, re.DOTALL):
        sel_id = sel_match.group(1)
        opts = re.findall(r'<option value="([^"]*)">(.*?)</option>', sel_match.group(2))
        filter_options[sel_id] = [{"value": v, "label": re.sub(r'<[^>]+>', '', l).strip()} for v, l in opts]
    data["filters"] = filter_options

    # ── 8. CSS (extract complete stylesheet) ──
    css_match = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
    data["css"] = css_match.group(1) if css_match else ""

    # ── 9. Google Fonts link ──
    fonts_match = re.search(r'(<link[^>]*fonts\.googleapis\.com[^>]*>)', html)
    data["fonts_link"] = fonts_match.group(1) if fonts_match else ""

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ 数据已提取到 {DATA_PATH}")
    print(f"   项目总览: {len(data['projects'])} 行")
    print(f"   收益台账: {len(data['income'])} 行")
    print(f"   拖欠明细: {len(data['arrears'])} 行")
    print(f"   分配明细: {len(data['distribution'])} 行")
    print(f"   光伏看板: {len(data['solar'])} 个卡片")

if __name__ == '__main__':
    extract_data()
