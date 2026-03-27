#!/usr/bin/env python3
"""
帮扶项目收益管理 CLI 工具
用法：python3 pam.py <action> [参数...]
所有输出为 JSON，方便大模型解析后呈现给用户。
"""
import sys
import json
import argparse
from datetime import date


def _import_db():
    try:
        from db import get_conn, get_cursor, init_db
        from periods import generate_periods
        return get_conn, get_cursor, init_db, generate_periods
    except ImportError as e:
        _fail("依赖缺失：" + str(e) + "，请执行 pip install psycopg2-binary python-dateutil")


def _ok(data, message=""):
    print(json.dumps({"status": "ok", "message": message, "data": data},
                     ensure_ascii=False, default=str))
    sys.exit(0)


def _fail(msg):
    print(json.dumps({"status": "error", "message": msg, "data": None},
                     ensure_ascii=False))
    sys.exit(1)


def fuzzy_find_project(cur, keyword):
    cur.execute("SELECT id, name FROM pam_projects WHERE name LIKE %s ORDER BY name",
                ("%" + keyword + "%",))
    return cur.fetchall()


def auto_refresh_periods(cur, project_id=None, until_year=None):
    from periods import generate_periods
    if project_id:
        cur.execute("SELECT * FROM pam_projects WHERE id=%s", (project_id,))
    else:
        cur.execute("SELECT * FROM pam_projects")
    projects = cur.fetchall()
    total = 0
    for p in projects:
        n = generate_periods(
            cur, p["id"], p["name"],
            p["contract_start"], p["contract_end"],
            float(p["agreed_income"]), p["income_frequency"],
            until_year=until_year
        )
        total += n
    return total


# ── Actions ──────────────────────────────────────────────────────────────────

def action_init(args):
    get_conn, get_cursor, init_db, generate_periods = _import_db()
    init_db()
    _ok({}, "数据库初始化成功")


def action_query_arrears(args):
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        auto_refresh_periods(cur)
        conn.commit()
        cur.execute("""
            SELECT project_name AS proj, period_label AS period,
                   due_amount AS due, paid_amount AS paid, arrear_amount AS arrear
            FROM pam_income_records
            WHERE arrear_amount > 0 AND period_end <= CURRENT_DATE
            ORDER BY project_name, period_start
        """)
        rows = []
        for r in cur.fetchall():
            rows.append({
                "项目名称": r["proj"],
                "收益周期": r["period"],
                "应缴金额": float(r["due"]),
                "实缴金额": float(r["paid"]),
                "拖欠金额": float(r["arrear"]),
            })
        total = sum(r["拖欠金额"] for r in rows)
        _ok({"records": rows, "total_arrear": round(total, 4), "count": len(rows)})
    finally:
        cur.close()
        conn.close()


def action_query_projects(args):
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        auto_refresh_periods(cur)
        conn.commit()
        cur.execute("""
            SELECT p.name, p.villages, p.operator,
                   p.contract_start, p.contract_end,
                   p.agreed_income, p.income_frequency,
                   COUNT(r.id) AS total_periods,
                   COALESCE(SUM(r.due_amount),0) AS total_due,
                   COALESCE(SUM(r.paid_amount),0) AS total_paid,
                   COALESCE(SUM(r.arrear_amount),0) AS total_arrear
            FROM pam_projects p
            LEFT JOIN pam_income_records r ON r.project_id = p.id
            GROUP BY p.id ORDER BY p.name
        """)
        _ok({"projects": [dict(r) for r in cur.fetchall()]})
    finally:
        cur.close()
        conn.close()


def action_query_income(args):
    if not args.project:
        _fail("缺少参数 --project")
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        auto_refresh_periods(cur)
        conn.commit()
        matches = fuzzy_find_project(cur, args.project)
        if not matches:
            _fail("未找到项目：" + args.project)
        if len(matches) > 1:
            _ok({"ambiguous": True, "candidates": [dict(m) for m in matches]},
                "匹配到多个项目，请确认")
        pid = matches[0]["id"]
        sql = """
            SELECT period_label, period_start, period_end,
                   due_amount, paid_amount, arrear_amount,
                   is_distributed, distributed_at, distributed_amount
            FROM pam_income_records WHERE project_id=%s
        """
        params = [pid]
        if args.period:
            sql += " AND period_label LIKE %s"
            params.append("%" + args.period + "%")
        sql += " ORDER BY period_start"
        cur.execute(sql, params)
        _ok({"project": matches[0]["name"],
             "records": [dict(r) for r in cur.fetchall()]})
    finally:
        cur.close()
        conn.close()


def action_query_distribution(args):
    if not args.project:
        _fail("缺少参数 --project")
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        matches = fuzzy_find_project(cur, args.project)
        if not matches:
            _fail("未找到项目：" + args.project)
        pid = matches[0]["id"]
        sql = """
            SELECT d.name,
                   LEFT(d.id_card,4)||'**********'||RIGHT(d.id_card,4) AS id_card_masked,
                   d.amount, d.bank_card, r.period_label, d.remark
            FROM pam_distribution_details d
            JOIN pam_income_records r ON r.id = d.income_record_id
            WHERE r.project_id = %s
        """
        params = [pid]
        if args.period:
            sql += " AND r.period_label LIKE %s"
            params.append("%" + args.period + "%")
        sql += " ORDER BY r.period_start, d.id"
        cur.execute(sql, params)
        _ok({"project": matches[0]["name"],
             "details": [dict(r) for r in cur.fetchall()]})
    finally:
        cur.close()
        conn.close()


def action_record_payment(args):
    if not args.project:
        _fail("缺少参数 --project")
    if args.amount is None:
        _fail("缺少参数 --amount（万元）")
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        auto_refresh_periods(cur)
        matches = fuzzy_find_project(cur, args.project)
        if not matches:
            conn.rollback()
            _fail("未找到项目：" + args.project)
        if len(matches) > 1:
            conn.rollback()
            _ok({"ambiguous": True, "candidates": [dict(m) for m in matches]},
                "匹配到多个项目，请确认")

        pid = matches[0]["id"]
        pname = matches[0]["name"]

        if args.period:
            cur.execute("""
                SELECT id, period_label, due_amount, paid_amount, arrear_amount
                FROM pam_income_records
                WHERE project_id=%s AND period_label LIKE %s
                ORDER BY period_start LIMIT 1
            """, (pid, "%" + args.period + "%"))
        else:
            cur.execute("""
                SELECT id, period_label, due_amount, paid_amount, arrear_amount
                FROM pam_income_records
                WHERE project_id=%s AND arrear_amount > 0
                ORDER BY period_start LIMIT 1
            """, (pid,))
        record = cur.fetchone()
        if not record:
            conn.rollback()
            _fail("项目【" + pname + "】无拖欠记录或未找到指定周期")

        pay_date = args.date or str(date.today())
        new_paid = float(record["paid_amount"]) + float(args.amount)
        cur.execute("""
            UPDATE pam_income_records SET paid_amount=%s, updated_at=NOW() WHERE id=%s
        """, (new_paid, record["id"]))

        cur.execute("""
            SELECT period_label, due_amount, paid_amount, arrear_amount
            FROM pam_income_records WHERE id=%s
        """, (record["id"],))
        updated = dict(cur.fetchone())
        conn.commit()
        _ok({
            "project": pname,
            "period": record["period_label"],
            "payment_date": pay_date,
            "this_payment": float(args.amount),
            "due_amount": float(updated["due_amount"]),
            "paid_amount": float(updated["paid_amount"]),
            "arrear_amount": float(updated["arrear_amount"]),
            "settled": float(updated["arrear_amount"]) <= 0
        }, "缴款记录成功")
    except Exception as e:
        conn.rollback()
        _fail(str(e))
    finally:
        cur.close()
        conn.close()


def action_record_distribution(args):
    if not args.project:
        _fail("缺少参数 --project")
    if args.amount is None:
        _fail("缺少参数 --amount（万元）")
    if not args.list:
        _fail("缺少参数 --list（分配名单JSON）")
    try:
        dist_list = json.loads(args.list)
    except Exception:
        _fail("--list 参数必须是合法 JSON 数组")

    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        matches = fuzzy_find_project(cur, args.project)
        if not matches:
            _fail("未找到项目：" + args.project)
        if len(matches) > 1:
            _ok({"ambiguous": True, "candidates": [dict(m) for m in matches]},
                "匹配到多个项目，请确认")

        pid = matches[0]["id"]
        pname = matches[0]["name"]

        cur.execute("""
            SELECT id, period_label FROM pam_income_records
            WHERE project_id=%s AND is_distributed=FALSE
            ORDER BY period_start DESC LIMIT 1
        """, (pid,))
        record = cur.fetchone()
        if not record:
            conn.rollback()
            _fail("项目【" + pname + "】无待分配的收益记录")

        dist_date = args.date or str(date.today())
        cur.execute("""
            UPDATE pam_income_records
            SET is_distributed=TRUE, distributed_at=%s, distributed_amount=%s, updated_at=NOW()
            WHERE id=%s
        """, (dist_date, float(args.amount), record["id"]))

        inserted = 0
        errors = []
        for item in dist_list:
            try:
                cur.execute("""
                    INSERT INTO pam_distribution_details
                        (income_record_id, project_name, period_label,
                         name, id_card, amount, bank_card, remark)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    record["id"], pname, record["period_label"],
                    item.get("name", ""),
                    item.get("id_card", ""),
                    float(item.get("amount", 0)),
                    item.get("bank_card", ""),
                    item.get("remark", "")
                ))
                inserted += 1
            except Exception as e:
                errors.append({"item": item, "error": str(e)})

        conn.commit()
        _ok({
            "project": pname,
            "period": record["period_label"],
            "distributed_at": dist_date,
            "total_amount": float(args.amount),
            "household_count": inserted,
            "errors": errors
        }, "分配到户记录成功，共 " + str(inserted) + " 户")
    except Exception as e:
        conn.rollback()
        _fail(str(e))
    finally:
        cur.close()
        conn.close()


def action_create_project(args):
    if not args.data:
        _fail("缺少参数 --data（项目JSON）")
    try:
        d = json.loads(args.data)
    except Exception:
        _fail("--data 参数必须是合法 JSON")

    required = ["name", "contract_start", "contract_end", "agreed_income"]
    missing = [f for f in required if not d.get(f)]
    if missing:
        _fail("缺少必填字段：" + str(missing))

    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            INSERT INTO pam_projects
                (name, villages, content, investment, operator,
                 contract_start, contract_end, agreed_income,
                 income_frequency, attachment_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (name) DO UPDATE SET
                villages=EXCLUDED.villages, content=EXCLUDED.content,
                investment=EXCLUDED.investment, operator=EXCLUDED.operator,
                contract_start=EXCLUDED.contract_start,
                contract_end=EXCLUDED.contract_end,
                agreed_income=EXCLUDED.agreed_income,
                income_frequency=EXCLUDED.income_frequency,
                attachment_path=EXCLUDED.attachment_path,
                updated_at=NOW()
            RETURNING id, name
        """, (
            d["name"],
            d.get("villages"),
            d.get("content"),
            d.get("investment"),
            d.get("operator"),
            d["contract_start"],
            d["contract_end"],
            float(d["agreed_income"]),
            d.get("income_frequency", "year"),
            d.get("attachment_path")
        ))
        project = dict(cur.fetchone())

        from datetime import date as _date
        from periods import generate_periods as _gp
        n = _gp(cur, project["id"], project["name"],
                _date.fromisoformat(d["contract_start"]),
                _date.fromisoformat(d["contract_end"]),
                float(d["agreed_income"]),
                d.get("income_frequency", "year"))
        conn.commit()
        _ok({"project": project, "periods_generated": n},
            "项目【" + project["name"] + "】创建成功，已生成 " + str(n) + " 个收益周期")
    except Exception as e:
        conn.rollback()
        _fail(str(e))
    finally:
        cur.close()
        conn.close()


def action_refresh_periods(args):
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        pid = None
        if args.project:
            matches = fuzzy_find_project(cur, args.project)
            if not matches:
                _fail("未找到项目：" + args.project)
            pid = matches[0]["id"]
        n = auto_refresh_periods(cur, pid)
        conn.commit()
        _ok({"new_periods": n}, "新增 " + str(n) + " 个收益周期记录")
    finally:
        cur.close()
        conn.close()


def action_generate_periods_year(args):
    """手动生成指定年份的收益周期"""
    if not args.year:
        _fail("缺少参数 --year（年份，如 2026）")
    year = int(args.year)
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        pid = None
        pname = "全部项目"
        if args.project:
            matches = fuzzy_find_project(cur, args.project)
            if not matches:
                _fail("未找到项目：" + args.project)
            pid = matches[0]["id"]
            pname = matches[0]["name"]
        n = auto_refresh_periods(cur, pid, until_year=year)
        conn.commit()
        _ok({"year": year, "project": pname, "new_periods": n},
            "已为" + pname + "生成 " + str(year) + " 年的收益周期，新增 " + str(n) + " 条")
    finally:
        cur.close()
        conn.close()


def groupSimilarProjects(projects):
    """按项目名称模式分组：去掉村名前缀后相同名称的项目归为一组"""
    import re
    def base_name(name):
        # 去掉开头的村名（如"东仇村"、"焦河村"）
        n = re.sub(r'^.+?村', '', name)
        return n.strip()
    groups = {}
    for p in projects:
        bn = base_name(p['name'])
        groups.setdefault(bn, []).append(p)
    return {k: v for k, v in groups.items() if len(v) > 1}

def action_export_html(args):
    """导出可视化查询页面（静态HTML）"""
    import os
    import subprocess
    get_conn, get_cursor, init_db, _ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        auto_refresh_periods(cur)
        conn.commit()

        # 查所有项目
        cur.execute("""
            SELECT p.id, p.name, p.villages, p.operator,
                   p.contract_start, p.contract_end,
                   p.agreed_income, p.income_frequency,
                   COUNT(r.id) AS total_periods,
                   COALESCE(SUM(r.due_amount),0) AS total_due,
                   COALESCE(SUM(r.paid_amount),0) AS total_paid,
                   COALESCE(SUM(r.arrear_amount),0) AS total_arrear
            FROM pam_projects p
            LEFT JOIN pam_income_records r ON r.project_id = p.id
            GROUP BY p.id ORDER BY p.name
        """)
        projects_raw = [dict(r) for r in cur.fetchall()]

        # 查所有收益记录（is_future 基于 period_start 判断）
        cur.execute("""
            SELECT r.project_name, r.period_label,
                   r.period_start, r.period_end,
                   r.due_amount, r.paid_amount, r.arrear_amount,
                   r.is_distributed, r.distributed_at, r.distributed_amount,
                   CASE WHEN r.period_start > CURRENT_DATE THEN TRUE ELSE FALSE END AS is_future
            FROM pam_income_records r
            ORDER BY r.project_name, r.period_start
        """)
        income_records = [dict(r) for r in cur.fetchall()]

        # 查拖欠记录
        cur.execute("""
            SELECT project_name AS proj, period_label AS period,
                   period_start, period_end,
                   due_amount AS due, paid_amount AS paid, arrear_amount AS arrear
            FROM pam_income_records
            WHERE arrear_amount > 0
            ORDER BY project_name, period_start
        """)
        arrears = [dict(r) for r in cur.fetchall()]

        # 计算 sub_projects：同模式项目归组
        groups = groupSimilarProjects(projects_raw)
        # 给每个项目添加 sub_projects 字段
        projects = []
        for p in projects_raw:
            p2 = dict(p)
            p2['sub_projects'] = []
            for bn, members in groups.items():
                if any(m['id'] == p['id'] for m in members):
                    p2['sub_projects'] = [
                        {"name": m['name'], "villages": m['villages'], "operator": m['operator']}
                        for m in members if m['id'] != p['id']
                    ]
                    break
            projects.append(p2)

        # 生成 HTML
        html = _build_dashboard_html(projects, income_records, arrears)

        # 写入文件
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "dashboard.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        _ok({"file": output_path}, "可视化页面已生成：" + output_path)
    finally:
        cur.close()
        conn.close()


def _build_dashboard_html(projects, income_records, arrears):
    """构建可视化 HTML 页面（含子项目合并逻辑）"""
    p_json = json.dumps(projects, ensure_ascii=False, default=str)
    i_json = json.dumps(income_records, ensure_ascii=False, default=str)
    a_json = json.dumps(arrears, ensure_ascii=False, default=str)
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>\u5e2e\u6276\u9879\u76ee\u6536\u76ca\u7ba1\u7406</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f2f5;color:#333}
.header{background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;padding:24px 32px;box-shadow:0 2px 8px rgba(0,0,0,.15)}
.header h1{font-size:24px;font-weight:600}
.header p{font-size:14px;opacity:.85;margin-top:4px}
.nav{display:flex;gap:0;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.08);position:sticky;top:0;z-index:100}
.nav button{flex:1;padding:14px 20px;border:none;background:none;font-size:15px;cursor:pointer;color:#666;border-bottom:3px solid transparent;transition:all .2s}
.nav button:hover{color:#1a73e8;background:#f5f8ff}
.nav button.active{color:#1a73e8;border-bottom-color:#1a73e8;font-weight:600}
.container{max-width:1200px;margin:20px auto;padding:0 16px}
.card{background:#fff;border-radius:12px;box-shadow:0 1px 6px rgba(0,0,0,.06);padding:20px;margin-bottom:16px}
.card h2{font-size:18px;color:#1a73e8;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #e8eaed}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}
.stat-card{background:linear-gradient(135deg,#f8f9ff,#e8f0fe);border-radius:10px;padding:16px;text-align:center}
.stat-card .num{font-size:28px;font-weight:700;color:#1a73e8}
.stat-card .label{font-size:13px;color:#666;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{background:#f8f9fa;padding:10px 12px;text-align:left;font-weight:600;color:#555;border-bottom:2px solid #e0e0e0;position:sticky;top:48px}
td{padding:10px 12px;border-bottom:1px solid #eee}
tr:hover td{background:#f5f8ff}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:500}
.badge-ok{background:#e6f4ea;color:#137333}
.badge-warn{background:#fef7e0;color:#b06000}
.badge-danger{background:#fce8e6;color:#c5221f}
.badge-future{background:#e8eaed;color:#5f6368}
.filter-bar{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.filter-bar select,.filter-bar input{padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none}
.filter-bar select:focus,.filter-bar input:focus{border-color:#1a73e8;box-shadow:0 0 0 2px rgba(26,115,232,.15)}
.tab-content{display:none}
.tab-content.active{display:block}
.amount{text-align:right;font-variant-numeric:tabular-nums}
.amount-neg{color:#c5221f;font-weight:600}
.amount-pos{color:#137333}
.project-card{display:flex;justify-content:space-between;align-items:center;padding:16px;border:1px solid #e8eaed;border-radius:10px;margin-bottom:12px;cursor:pointer;transition:all .2s}
.project-card:hover{border-color:#1a73e8;box-shadow:0 2px 8px rgba(26,115,232,.12)}
.project-card .proj-name{font-size:16px;font-weight:600;color:#1a73e8}
.project-card .proj-info{font-size:13px;color:#888;margin-top:4px}
.project-card .proj-stats{text-align:right}
.project-card .proj-stats .due{font-size:14px;color:#666}
.project-card .proj-stats .arrear{font-size:14px;color:#c5221f;font-weight:600}
.empty{text-align:center;padding:40px;color:#999;font-size:15px}
@media(max-width:768px){.nav button{font-size:13px;padding:10px 8px}.container{padding:0 8px}th,td{padding:6px 8px;font-size:12px}}
</style>
</head>
<body>
<div class="header">
<h1>&#x1f4ca; &#x5e2e;&#x6276;&#x9879;&#x76ee;&#x6536;&#x76ca;&#x7ba1;&#x7406;</h1>
<p>&#x6570;&#x636e;&#x770b;&#x677f; &middot; &#x652f;&#x6301;&#x9879;&#x76ee;&#x67e5;&#x8be2;&#x3001;&#x6536;&#x76ca;&#x660e;&#x7ec6;&#x3001;&#x62d6;&#x6b20;&#x660e;&#x7ec6;</p>
</div>
<div class="nav">
<button class="active" onclick="showTab('projects')">&#x1f4cb; &#x9879;&#x76ee;&#x6982;&#x89c8;</button>
<button onclick="showTab('income')">&#x1f4c8; &#x6536;&#x76ca;&#x660e;&#x7ec6;</button>
<button onclick="showTab('future')">&#x1f4c5; &#x672a;&#x6765;&#x6536;&#x76ca;</button>
<button onclick="showTab('arrears')">&#x26a0;&#xfe0f; &#x62d6;&#x6b20;&#x660e;&#x7ec6;</button>
</div>
<div class="container">
<div id="tab-projects" class="tab-content active">
<div class="stats" id="summary-stats"></div>
<div class="card">
<h2>&#x9879;&#x76ee;&#x5217;&#x8868;</h2>
<div class="filter-bar">
<input type="text" id="proj-search" placeholder="&#x641c;&#x7d22;&#x9879;&#x76ee;&#x540d;&#x79f0;..." oninput="renderProjects()">
</div>
<div id="project-list"></div>
</div>
</div>
<div id="tab-income" class="tab-content">
<div class="card">
<h2>&#x6536;&#x76ca;&#x660e;&#x7ec6;</h2>
<div class="filter-bar">
<select id="income-proj-filter" onchange="renderIncome()"><option value="">&#x5168;&#x90e8;&#x9879;&#x76ee;</option></select>
<select id="income-status-filter" onchange="renderIncome()">
<option value="">&#x5168;&#x90e8;&#x72b6;&#x6001;</option>
<option value="arrear">&#x6709;&#x62d6;&#x6b20;</option>
<option value="settled">&#x5df2;&#x7ed3;&#x6e05;</option>
<option value="undistributed">&#x672a;&#x5206;&#x914d;</option>
</select>
</div>
<div style="overflow-x:auto"><table><thead><tr>
<th>&#x9879;&#x76ee;&#x540d;&#x79f0;</th><th>&#x6d89;&#x53ca;&#x6751;</th><th>&#x6536;&#x76ca;&#x5468;&#x671f;</th><th class="amount">&#x5e94;&#x7f34;(&#x4e07;&#x5143;)</th>
<th class="amount">&#x5b9e;&#x7f34;(&#x4e07;&#x5143;)</th><th class="amount">&#x62d6;&#x6b20;(&#x4e07;&#x5143;)</th><th>&#x5206;&#x914d;&#x72b6;&#x6001;</th>
</tr></thead><tbody id="income-tbody"></tbody></table></div>
</div>
</div>
<div id="tab-future" class="tab-content">
<div class="card">
<h2>&#x672a;&#x6765;&#x6536;&#x76ca;</h2>
<div class="filter-bar">
<select id="future-proj-filter" onchange="renderFuture()"><option value="">&#x5168;&#x90e8;&#x9879;&#x76ee;</option></select>
</div>
<div style="overflow-x:auto"><table><thead><tr>
<th>&#x9879;&#x76ee;&#x540d;&#x79f0;</th><th>&#x6536;&#x76ca;&#x5468;&#x671f;</th><th class="amount">&#x9884;&#x8ba1;&#x5e94;&#x7f34;(&#x4e07;&#x5143;)</th>
</tr></thead><tbody id="future-tbody"></tbody></table></div>
</div>
</div>
<div id="tab-arrears" class="tab-content">
<div class="stats" id="arrear-stats"></div>
<div class="card">
<h2>&#x62d6;&#x6b20;&#x660e;&#x7ec6;</h2>
<div class="filter-bar">
<select id="arrear-proj-filter" onchange="renderArrears()"><option value="">&#x5168;&#x90e8;&#x9879;&#x76ee;</option></select>
</div>
<div style="overflow-x:auto"><table><thead><tr>
<th>&#x9879;&#x76ee;&#x540d;&#x79f0;</th><th>&#x6536;&#x76ca;&#x5468;&#x671f;</th><th class="amount">&#x5e94;&#x7f34;(&#x4e07;&#x5143;)</th>
<th class="amount">&#x5b9e;&#x7f34;(&#x4e07;&#x5143;)</th><th class="amount">&#x62d6;&#x6b20;(&#x4e07;&#x5143;)</th><th>&#x8d1f;&#x8d23;&#x4eba;</th>
</tr></thead><tbody id="arrear-tbody"></tbody></table></div>
</div>
</div>
</div>
<script>
const projects=""" + p_json + """;
const incomeRecords=""" + i_json + """;
const arrears=""" + a_json + """;

function fmt(v){return Number(v).toFixed(2)}
function fmtDate(s){if(!s)return'-';const d=new Date(s);return d.getFullYear()+'.'+(d.getMonth()+1)+'.'+d.getDate()}

function getMergedName(rn){
  for(const p of projects){
    if(p.name===rn)return rn.replace(/.+?村/,'');
    if(p.sub_projects&&p.sub_projects.some(s=>s.name===rn))return p.name.replace(/.+?村/,'');
  }
  return rn;
}
function getMergedPillarName(rn){
  for(const p of projects){
    if(p.name===rn)return p.villages||'';
    if(p.sub_projects){
      const s=p.sub_projects.find(s=>s.name===rn);
      if(s)return s.villages||'';
    }
  }
  return '';
}
function getMergedOperator(rn){
  for(const p of projects){
    if(p.name===rn)return p.operator||'';
    if(p.sub_projects){
      const s=p.sub_projects.find(s=>s.name===rn);
      if(s)return s.operator||'';
    }
  }
  return '';
}
function groupMerged(records){
  const map={};
  for(const r of records){
    const mn=getMergedName(r.project_name);
    const k=mn+'|'+r.period_label;
    if(!map[k]){
      map[k]={project_name:mn,period_label:r.period_label,
        due_amount:0,paid_amount:0,arrear_amount:0,
        is_distributed:true,distributed_at:r.distributed_at||null,
        is_future:!!r.is_future,
        villages:getMergedPillarName(r.project_name)};
    }
    const g=map[k];
    g.due_amount=Number(g.due_amount)+Number(r.due_amount);
    g.paid_amount=Number(g.paid_amount)+Number(r.paid_amount);
    g.arrear_amount=Number(g.arrear_amount)+Number(r.arrear_amount);
    if(!r.is_distributed)g.is_distributed=false;
  }
  return Object.values(map);
}

function showTab(name){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.nav button').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  document.querySelectorAll('.nav button')[['projects','income','future','arrears'].indexOf(name)].classList.add('active');
}

function renderProjects(){
  const q=document.getElementById('proj-search').value.toLowerCase();
  const filtered=projects.filter(p=>!q||p.name.toLowerCase().includes(q));
  const totalDue=filtered.reduce((s,p)=>s+Number(p.total_due),0);
  const totalPaid=filtered.reduce((s,p)=>s+Number(p.total_paid),0);
  const totalArrear=filtered.reduce((s,p)=>s+Number(p.total_arrear),0);
  document.getElementById('summary-stats').innerHTML=
    '<div class="stat-card"><div class="num">'+filtered.length+'</div><div class="label">\u9879\u76ee\u603b\u6570</div></div>'+
    '<div class="stat-card"><div class="num">'+fmt(totalDue)+'</div><div class="label">\u5e94\u6536\u603b\u989d(\u4e07\u5143)</div></div>'+
    '<div class="stat-card"><div class="num">'+fmt(totalPaid)+'</div><div class="label">\u5df2\u6536\u603b\u989d(\u4e07\u5143)</div></div>'+
    '<div class="stat-card"><div class="num" style="color:'+(totalArrear>0?'#c5221f':'#137333')+'">'+fmt(totalArrear)+'</div><div class="label">\u62d6\u6b20\u603b\u989d(\u4e07\u5143)</div></div>';
  const el=document.getElementById('project-list');
  if(!filtered.length){el.innerHTML='<div class="empty">\u65e0\u5339\u914d\u9879\u76ee</div>';return}
  el.innerHTML=filtered.map((p,i)=>{
    const arrear=Number(p.total_arrear);
    const villages=p.villages?(typeof p.villages==='string'?p.villages:p.villages.join(', ')):'';
    const subs=p.sub_projects&&p.sub_projects.length?'<br>\u5b50\u9879\u76ee: '+p.sub_projects.map(s=>s.name).join(', '):'';
    return '<div class="project-card" data-idx="'+i+'" onclick="viewProject('+i+')">'+
      '<div><div class="proj-name">'+p.name+'</div>'+
      '<div class="proj-info">'+(p.operator||'')+' \u00b7 '+(villages||'')+' \u00b7 \u5408\u540c '+fmtDate(p.contract_start)+'~'+fmtDate(p.contract_end)+subs+'</div></div>'+
      '<div class="proj-stats"><div class="due">\u5e94\u6536 '+fmt(p.total_due)+' \u4e07</div>'+
      '<div class="arrear">'+(arrear>0?'\u62d6\u6b20 '+fmt(arrear)+' \u4e07':'<span style="color:#137333">\u5df2\u7ed3\u6e05</span>')+'</div></div></div>'}).join('');
  el._filtered=filtered;
}

function viewProject(idx){
  const list=document.getElementById('project-list');
  const p=list._filtered?list._filtered[idx]:null;
  if(!p)return;
  const mn=getMergedName(p.name);
  document.getElementById('income-proj-filter').value=mn;
  showTab('income');
  renderIncome();
}

function renderIncome(){
  const projFilter=document.getElementById('income-proj-filter').value;
  const statusFilter=document.getElementById('income-status-filter').value;
  let merged=groupMerged(incomeRecords.filter(r=>!r.is_future));
  if(projFilter)merged=merged.filter(r=>r.project_name===projFilter);
  if(statusFilter==='arrear')merged=merged.filter(r=>Number(r.arrear_amount)>0);
  if(statusFilter==='settled')merged=merged.filter(r=>Number(r.arrear_amount)<=0);
  if(statusFilter==='undistributed')merged=merged.filter(r=>!r.is_distributed);
  const el=document.getElementById('income-tbody');
  if(!merged.length){el.innerHTML='<tr><td colspan="7" class="empty">\u65e0\u5339\u914d\u8bb0\u5f55</td></tr>';return}
  el.innerHTML=merged.map(r=>{
    const arrear=Number(r.arrear_amount);
    const status=arrear>0?'<span class="badge badge-danger">\u62d6\u6b20</span>':
      r.is_distributed?'<span class="badge badge-ok">\u5df2\u5206\u914d</span>':
      '<span class="badge badge-warn">\u5f85\u5206\u914d</span>';
    return '<tr><td>'+r.project_name+'</td><td>'+(r.villages||'')+'</td><td>'+r.period_label+'</td>'+
      '<td class="amount">'+fmt(r.due_amount)+'</td>'+
      '<td class="amount">'+fmt(r.paid_amount)+'</td>'+
      '<td class="amount '+(arrear>0?'amount-neg':'amount-pos')+'">'+fmt(r.arrear_amount)+'</td>'+
      '<td>'+status+'</td></tr>'}).join('');
}

function renderFuture(){
  const projFilter=document.getElementById('future-proj-filter').value;
  let merged=groupMerged(incomeRecords.filter(r=>r.is_future));
  if(projFilter)merged=merged.filter(r=>r.project_name===projFilter);
  const el=document.getElementById('future-tbody');
  if(!merged.length){el.innerHTML='<tr><td colspan="3" class="empty">\u65e0\u672a\u6765\u6536\u76ca\u8bb0\u5f55</td></tr>';return}
  el.innerHTML=merged.map(r=>'<tr><td>'+r.project_name+'</td><td>'+r.period_label+'</td>'+
    '<td class="amount">'+fmt(r.due_amount)+'</td></tr>').join('');
}

function renderArrears(){
  const projFilter=document.getElementById('arrear-proj-filter').value;
  let filtered=arrears;
  if(projFilter)filtered=filtered.filter(r=>r.proj===projFilter);
  const total=filtered.reduce((s,r)=>s+Number(r.arrear),0);
  document.getElementById('arrear-stats').innerHTML=
    '<div class="stat-card"><div class="num" style="color:#c5221f">'+filtered.length+'</div><div class="label">\u62d6\u6b20\u7b14\u6570</div></div>'+
    '<div class="stat-card"><div class="num" style="color:#c5221f">'+fmt(total)+'</div><div class="label">\u62d6\u6b20\u603b\u989d(\u4e07\u5143)</div></div>';
  const el=document.getElementById('arrear-tbody');
  if(!filtered.length){el.innerHTML='<tr><td colspan="6" class="empty">&#x1F389; \u65e0\u62d6\u6b20\u8bb0\u5f55</td></tr>';return}
  el.innerHTML=filtered.map(r=>'<tr><td>'+r.proj+'</td><td>'+r.period+'</td>'+
    '<td class="amount">'+fmt(r.due)+'</td><td class="amount">'+fmt(r.paid)+'</td>'+
    '<td class="amount amount-neg">'+fmt(r.arrear)+'</td><td>'+getMergedOperator(r.proj)+'</td></tr>').join('');
}

function initFilters(){
  const mergedIncome=groupMerged(incomeRecords);
  const projs=[...new Set(mergedIncome.map(r=>r.project_name))];
  const projNames=[...new Set(arrears.map(r=>r.proj))];
  const sel1=document.getElementById('income-proj-filter');
  const sel2=document.getElementById('arrear-proj-filter');
  const sel3=document.getElementById('future-proj-filter');
  projs.forEach(p=>{sel1.innerHTML+='<option value="'+p+'">'+p+'</option>'});
  projNames.forEach(p=>{sel2.innerHTML+='<option value="'+p+'">'+p+'</option>'});
  projs.forEach(p=>{sel3.innerHTML+='<option value="'+p+'">'+p+'</option>'});
}

initFilters();
renderProjects();
renderIncome();
renderFuture();
renderArrears();
</script>
</body>
</html>"""
    return html
def main():
    parser = argparse.ArgumentParser(description="帮扶项目收益管理 CLI")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("init",           help="初始化数据库")
    sub.add_parser("query_arrears",  help="查询拖欠情况")
    sub.add_parser("query_projects", help="查询所有项目")

    p = sub.add_parser("query_income")
    p.add_argument("--project", required=True)
    p.add_argument("--period")

    p = sub.add_parser("query_distribution")
    p.add_argument("--project", required=True)
    p.add_argument("--period")

    p = sub.add_parser("record_payment")
    p.add_argument("--project", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--date")
    p.add_argument("--period")

    p = sub.add_parser("record_distribution")
    p.add_argument("--project", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--date")
    p.add_argument("--list", required=True)

    p = sub.add_parser("create_project")
    p.add_argument("--data", required=True)

    p = sub.add_parser("refresh_periods")
    p.add_argument("--project")

    p = sub.add_parser("generate_periods_year")
    p.add_argument("--year", required=True, type=int)
    p.add_argument("--project")

    sub.add_parser("export_html", help="导出可视化查询页面")

    args = parser.parse_args()

    actions = {
        "init":                  action_init,
        "query_arrears":         action_query_arrears,
        "query_projects":        action_query_projects,
        "query_income":          action_query_income,
        "query_distribution":    action_query_distribution,
        "record_payment":        action_record_payment,
        "record_distribution":   action_record_distribution,
        "create_project":        action_create_project,
        "refresh_periods":       action_refresh_periods,
        "generate_periods_year": action_generate_periods_year,
        "export_html":           action_export_html,
    }

    if args.action not in actions:
        parser.print_help()
        sys.exit(1)

    actions[args.action](args)


if __name__ == "__main__":
    main()
