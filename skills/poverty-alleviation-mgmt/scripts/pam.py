#!/usr/bin/env python3
"""
帮扶项目收益管理 CLI 工具
用法：python3 pam.py <action> [参数...]
所有输出为 JSON，方便大模型解析后呈现给用户。

Actions:
  init
  query_arrears
  query_projects
  query_income  --project <名称> [--period <关键词>]
  query_distribution --project <名称> [--period <关键词>]
  record_payment  --project <名称> --amount <万元> [--date <YYYY-MM-DD>] [--period <关键词>]
  record_distribution --project <名称> --amount <万元> [--date <YYYY-MM-DD>] --list <名单JSON>
  create_project  --data <项目JSON>
  generate_year   --year <年份> [--project <名称>]
  build_dashboard                         生成看板HTML并推送GitHub
"""
import sys
import json
import argparse
from datetime import date


def _import_db():
    try:
        from db import get_conn, get_cursor, init_db
        from periods import generate_periods_initial, generate_periods_for_year
        return get_conn, get_cursor, init_db, generate_periods_initial, generate_periods_for_year
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


# ── Actions ──────────────────────────────────────────────────────────────────

def action_init(args):
    get_conn, get_cursor, init_db, _, __ = _import_db()
    init_db()
    _ok({}, "数据库初始化成功")


def action_query_arrears(args):
    get_conn, get_cursor, init_db, _, __ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        conn.commit()
        cur.execute("""
            SELECT project_name AS proj, period_label AS period,
                   period_start, period_end,
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
    get_conn, get_cursor, init_db, _, __ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute("""
            SELECT p.name, p.villages, p.operator,
                   p.contract_start, p.contract_end,
                   p.agreed_income, p.income_frequency,
                   COUNT(r.id) AS total_periods,
                   COALESCE(SUM(CASE WHEN r.period_end <= CURRENT_DATE THEN r.due_amount ELSE 0 END),0) AS total_due,
                   COALESCE(SUM(r.paid_amount),0) AS total_paid,
                   COALESCE(SUM(CASE WHEN r.period_end <= CURRENT_DATE THEN r.arrear_amount ELSE 0 END),0) AS total_arrear
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
    get_conn, get_cursor, init_db, _, __ = _import_db()
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
        sql = """
            SELECT period_label, period_start, period_end,
                   due_amount, paid_amount, arrear_amount,
                   is_distributed, distributed_at, distributed_amount,
                   remark
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
    get_conn, get_cursor, init_db, _, __ = _import_db()
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
    get_conn, get_cursor, init_db, _, __ = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
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
                WHERE project_id=%s AND arrear_amount > 0 AND period_end <= CURRENT_DATE
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

        # 触发看板重建
        _trigger_dashboard_build(cur, conn)

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
    except SystemExit:
        raise
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

    get_conn, get_cursor, init_db, _, __ = _import_db()
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

        # 触发看板重建
        _trigger_dashboard_build(cur, conn)

        _ok({
            "project": pname,
            "period": record["period_label"],
            "distributed_at": dist_date,
            "total_amount": float(args.amount),
            "household_count": inserted,
            "errors": errors
        }, "分配到户记录成功，共 " + str(inserted) + " 户")
    except SystemExit:
        raise
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

    get_conn, get_cursor, init_db, gen_initial, _ = _import_db()
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
        n = gen_initial(cur, project["id"], project["name"],
                        _date.fromisoformat(d["contract_start"]),
                        _date.fromisoformat(d["contract_end"]),
                        float(d["agreed_income"]),
                        d.get("income_frequency", "year"))
        conn.commit()
        _ok({"project": project, "periods_generated": n},
            "项目【" + project["name"] + "】创建成功，已生成 " + str(n) + " 个收益周期（至当年年底）")
    except SystemExit:
        raise
    except Exception as e:
        conn.rollback()
        _fail(str(e))
    finally:
        cur.close()
        conn.close()


def action_generate_year(args):
    """手动为指定年份生成收益周期"""
    if not args.year:
        _fail("缺少参数 --year（年份，如 2025）")
    try:
        year = int(args.year)
    except ValueError:
        _fail("--year 必须是整数年份")

    get_conn, get_cursor, init_db, _, gen_year = _import_db()
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        from datetime import date as _date
        if args.project:
            matches = fuzzy_find_project(cur, args.project)
            if not matches:
                _fail("未找到项目：" + args.project)
            projects_to_process = matches
        else:
            cur.execute("SELECT id, name FROM pam_projects")
            projects_to_process = cur.fetchall()

        results = []
        for p in projects_to_process:
            cur.execute("SELECT * FROM pam_projects WHERE id=%s", (p["id"],))
            proj = cur.fetchone()
            n = gen_year(cur, proj["id"], proj["name"],
                         proj["contract_start"], proj["contract_end"],
                         float(proj["agreed_income"]), proj["income_frequency"],
                         year)
            results.append({"project": proj["name"], "new_periods": n})
        conn.commit()
        total = sum(r["new_periods"] for r in results)
        _ok({"year": year, "results": results, "total_new": total},
            str(year) + " 年收益周期生成完成，共新增 " + str(total) + " 条")
    except SystemExit:
        raise
    except Exception as e:
        conn.rollback()
        _fail(str(e))
    finally:
        cur.close()
        conn.close()


def action_build_dashboard(args):
    """生成可视化看板 HTML 并推送到 GitHub"""
    import os
    import subprocess
    import datetime
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dashboard_script = os.path.join(script_dir, "build_dashboard.py")
    if not os.path.exists(dashboard_script):
        _fail("未找到 build_dashboard.py，请确认脚本完整安装")
    result = subprocess.run(
        [sys.executable, dashboard_script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        _fail("看板生成失败：" + result.stderr[-500:])

    # 推送到 GitHub
    push_result = _push_dashboard_to_github()

    try:
        out = json.loads(result.stdout)
        if push_result:
            out["github"] = push_result
        print(json.dumps(out, ensure_ascii=False))
    except Exception:
        data = {"output": result.stdout[:500]}
        if push_result:
            data["github"] = push_result
        _ok(data, "看板已生成")
    sys.exit(0)


def _push_dashboard_to_github():
    """将 dashboard.html 推送到 amnesiacer/main 仓库，返回 GitHub URL 或错误"""
    import os
    import shutil
    import subprocess
    import datetime

    repo_dir = '/tmp/main_repo'
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(script_dir, '..', 'dashboard.html')

    # 确保仓库存在
    if not os.path.isdir(repo_dir):
        init_result = subprocess.run(
            ['git', 'clone', '--depth', '1', 'git@github.com:amnesiacer/main.git', repo_dir],
            capture_output=True, text=True
        )
        if init_result.returncode != 0:
            return f"❌ 仓库克隆失败: {init_result.stderr}"

    try:
        shutil.copy2(src, os.path.join(repo_dir, 'dashboard.html'))
        shutil.copy2(src, os.path.join(repo_dir, 'index.html'))
    except Exception as e:
        return f"❌ 文件复制失败: {e}"

    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def git_cmd(cmd):
        return subprocess.run(cmd, shell=True, cwd=repo_dir, capture_output=True, text=True)

    git_cmd('git add dashboard.html index.html')
    diff = git_cmd('git diff --cached --quiet')
    if diff.returncode == 0:
        return "没有变更需要推送"

    git_cmd(f'git commit -m "自动更新看板 {now}"')
    push = git_cmd('git push origin main')
    if push.returncode != 0:
        return f"❌ 推送失败: {push.stderr[-300:]}"

    return "✅ 已推送到 https://amnesiacer.github.io/main/"


def _trigger_dashboard_build(cur, conn):
    """数据变更后静默触发看板重建（忽略错误）"""
    try:
        import os
        import subprocess
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dashboard_script = os.path.join(script_dir, "build_dashboard.py")
        if os.path.exists(dashboard_script):
            subprocess.Popen([sys.executable, dashboard_script],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # 看板生成后再推送 GitHub（静默）
            subprocess.Popen([sys.executable, __file__, '_push_internal'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ── 入口 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="帮扶项目收益管理 CLI")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("init",           help="初始化数据库")
    sub.add_parser("query_arrears",  help="查询拖欠情况（仅已到期）")
    sub.add_parser("query_projects", help="查询所有项目汇总")

    p = sub.add_parser("query_income")
    p.add_argument("--project", required=True)
    p.add_argument("--period")

    p = sub.add_parser("query_distribution")
    p.add_argument("--project", required=True)
    p.add_argument("--period")

    p = sub.add_parser("record_payment")
    p.add_argument("--project", required=True)
    p.add_argument("--amount", type=float, required=True, help="万元")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--period", help="指定周期（模糊匹配）")

    p = sub.add_parser("record_distribution")
    p.add_argument("--project", required=True)
    p.add_argument("--amount", type=float, required=True, help="万元")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--list", required=True,
                   help='JSON数组：[{"name":"张三","id_card":"...","amount":895900,"bank_card":"..."}]')

    p = sub.add_parser("create_project")
    p.add_argument("--data", required=True, help="项目JSON字符串")

    p = sub.add_parser("generate_year", help="为指定年份生成收益周期")
    p.add_argument("--year", required=True, help="年份，如 2025")
    p.add_argument("--project", help="指定项目（不填则所有项目）")

    sub.add_parser("build_dashboard", help="生成可视化看板并推送GitHub")
    sub.add_parser("_push_internal", help="内部使用：仅推送看板到GitHub")

    args = parser.parse_args()

    actions = {
        "init":                action_init,
        "query_arrears":       action_query_arrears,
        "query_projects":      action_query_projects,
        "query_income":        action_query_income,
        "query_distribution":  action_query_distribution,
        "record_payment":      action_record_payment,
        "record_distribution": action_record_distribution,
        "create_project":      action_create_project,
        "generate_year":       action_generate_year,
        "build_dashboard":     action_build_dashboard,
        "_push_internal":      lambda args: (_push_dashboard_to_github() or sys.exit(0)),
    }

    if args.action not in actions:
        parser.print_help()
        sys.exit(1)

    actions[args.action](args)


if __name__ == "__main__":
    main()
