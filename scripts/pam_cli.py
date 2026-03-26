#!/usr/bin/env python3
"""
帮扶项目收益管理 CLI 工具
用法: python pam_cli.py <action> [参数...]
所有输出为 JSON 格式，供大模型解读后呈现给用户。
"""

import sys
import json
import argparse
from datetime import date, datetime
from decimal import Decimal

# ── 依赖检查 ──────────────────────────────────────────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print(json.dumps({"success": False, "error": "缺少依赖: pip install psycopg2-binary python-dateutil --break-system-packages"}))
    sys.exit(1)

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    print(json.dumps({"success": False, "error": "缺少依赖: pip install python-dateutil --break-system-packages"}))
    sys.exit(1)

# ── 数据库连接 ────────────────────────────────────────────────────────────────
DB_URL = "postgresql://amnesiac:52Xiaofang@www.amnesiac.cn:15432/Mydates"

def get_conn():
    return psycopg2.connect(DB_URL)

# ── JSON 序列化辅助 ───────────────────────────────────────────────────────────
def json_serial(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def output(data):
    print(json.dumps(data, ensure_ascii=False, default=json_serial))

# ── 初始化数据库表 ─────────────────────────────────────────────────────────────
INIT_SQL = """
CREATE TABLE IF NOT EXISTS pam_projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,
    villages TEXT[],
    content TEXT,
    investment NUMERIC(15,2),
    operator VARCHAR(200),
    contract_start DATE,
    contract_end DATE,
    agreed_income NUMERIC(15,4),
    income_frequency VARCHAR(20) DEFAULT 'year',
    attachment_path TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pam_income_records (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES pam_projects(id) ON DELETE CASCADE,
    project_name VARCHAR(200),
    period_label VARCHAR(100),
    period_start DATE,
    period_end DATE,
    due_amount NUMERIC(15,4),
    paid_amount NUMERIC(15,4) DEFAULT 0,
    arrear_amount NUMERIC(15,4) GENERATED ALWAYS AS (due_amount - paid_amount) STORED,
    is_distributed BOOLEAN DEFAULT FALSE,
    distributed_at DATE,
    distributed_amount NUMERIC(15,4),
    remark TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, period_start)
);

CREATE TABLE IF NOT EXISTS pam_distribution_details (
    id SERIAL PRIMARY KEY,
    income_record_id INTEGER REFERENCES pam_income_records(id) ON DELETE CASCADE,
    project_name VARCHAR(200),
    period_label VARCHAR(100),
    name VARCHAR(100),
    id_card VARCHAR(18),
    amount NUMERIC(15,2),
    bank_card VARCHAR(30),
    remark TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_income_project ON pam_income_records(project_id);
CREATE INDEX IF NOT EXISTS idx_income_arrear ON pam_income_records(arrear_amount) WHERE arrear_amount > 0;
CREATE INDEX IF NOT EXISTS idx_dist_record ON pam_distribution_details(income_record_id);
"""

def ensure_tables(cur):
    cur.execute(INIT_SQL)

# ── 收益周期生成 ───────────────────────────────────────────────────────────────
def _generate_periods_for_project(cur, project):
    pid = project['id']
    freq = project['income_frequency'] or 'year'
    agreed = float(project['agreed_income'] or 0)
    start = project['contract_start']
    end = project['contract_end']

    delta_map = {
        'year':    relativedelta(years=1),
        'half':    relativedelta(months=6),
        'quarter': relativedelta(months=3),
        'month':   relativedelta(months=1),
    }
    count_map = {'year': 1, 'half': 2, 'quarter': 4, 'month': 12}

    def label_fn(s, freq):
        if freq == 'year':    return f"{s.year}年度"
        if freq == 'half':    return f"{s.year}年{'上' if s.month <= 6 else '下'}半年"
        if freq == 'quarter': return f"{s.year}年第{(s.month-1)//3+1}季度"
        if freq == 'month':   return f"{s.year}年{s.month:02d}月"

    delta = delta_map.get(freq, relativedelta(years=1))
    per_income = agreed / count_map.get(freq, 1)
    today = date.today()
    gen_until = min(end, today + delta)

    inserted = 0
    cur_start = start
    while cur_start <= gen_until:
        period_end = min(cur_start + delta - relativedelta(days=1), end)
        label = label_fn(cur_start, freq)
        cur.execute("""
            INSERT INTO pam_income_records
                (project_id, project_name, period_label, period_start, period_end, due_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, period_start) DO NOTHING
        """, (pid, project['name'], label, cur_start, period_end, per_income))
        inserted += cur.rowcount
        cur_start += delta
    return inserted

# ══════════════════════════════════════════════════════════════════════════════
# ACTION 处理函数
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. query_arrears ──────────────────────────────────────────────────────────
def action_query_arrears(args):
    """查询所有拖欠记录"""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)
        # 先滚动生成新周期
        cur.execute("SELECT * FROM pam_projects")
        projects = cur.fetchall()
        for p in projects:
            _generate_periods_for_project(cur, p)
        conn.commit()

        cur.execute("""
            SELECT 
                project_name, period_label, period_start,
                due_amount, paid_amount, arrear_amount
            FROM pam_income_records
            WHERE arrear_amount > 0 AND period_end <= CURRENT_DATE
            ORDER BY project_name, period_start
        """)
        rows = [dict(r) for r in cur.fetchall()]
        total = sum(float(r['arrear_amount']) for r in rows)
        output({"success": True, "action": "query_arrears",
                "records": rows, "total_arrear": round(total, 4),
                "count": len(rows)})
    except Exception as e:
        output({"success": False, "action": "query_arrears", "error": str(e)})
    finally:
        conn.close()


# ── 2. record_payment ─────────────────────────────────────────────────────────
def action_record_payment(args):
    """
    录入缴款
    必填: --project 项目名关键词  --amount 金额(万元)
    可选: --date 缴款日期(YYYY-MM-DD，默认今天)  --period 周期标签(可选，默认最早拖欠)
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)

        # 查找项目
        cur.execute("SELECT * FROM pam_projects WHERE name LIKE %s", (f'%{args.project}%',))
        projects = cur.fetchall()
        if not projects:
            output({"success": False, "action": "record_payment",
                    "error": f"未找到匹配项目：{args.project}",
                    "hint": "请检查项目名称是否正确"})
            return
        if len(projects) > 1:
            output({"success": False, "action": "record_payment",
                    "error": "匹配到多个项目，请提供更精确的项目名",
                    "matched_projects": [p['name'] for p in projects]})
            return

        project = projects[0]
        # 先更新周期
        _generate_periods_for_project(cur, project)

        # 找目标周期
        if args.period:
            cur.execute("""
                SELECT * FROM pam_income_records
                WHERE project_id=%s AND period_label=%s
            """, (project['id'], args.period))
        else:
            cur.execute("""
                SELECT * FROM pam_income_records
                WHERE project_id=%s AND arrear_amount > 0
                ORDER BY period_start LIMIT 1
            """, (project['id'],))

        record = cur.fetchone()
        if not record:
            output({"success": False, "action": "record_payment",
                    "error": f"该项目({project['name']})没有待缴费的收益周期"})
            return

        pay_date = args.date or date.today().isoformat()
        amount = float(args.amount)
        new_paid = float(record['paid_amount']) + amount
        new_arrear = float(record['due_amount']) - new_paid

        cur.execute("""
            UPDATE pam_income_records
            SET paid_amount = %s, updated_at = NOW()
            WHERE id = %s
        """, (new_paid, record['id']))
        conn.commit()

        output({
            "success": True,
            "action": "record_payment",
            "project_name": project['name'],
            "period_label": record['period_label'],
            "pay_date": pay_date,
            "this_payment": amount,
            "due_amount": float(record['due_amount']),
            "paid_amount": new_paid,
            "arrear_amount": round(new_arrear, 4),
            "settled": new_arrear <= 0
        })
    except Exception as e:
        conn.rollback()
        output({"success": False, "action": "record_payment", "error": str(e)})
    finally:
        conn.close()


# ── 3. record_distribution ───────────────────────────────────────────────────
def action_record_distribution(args):
    """
    记录分配到户
    必填: --project 项目名  --total 到户总金额(万元)  --list 名单JSON字符串
    名单格式: [{"name":"张三","id_card":"...","amount":895900,"bank_card":"...","remark":""}]
    可选: --date 分配日期  --period 周期标签
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)

        cur.execute("SELECT * FROM pam_projects WHERE name LIKE %s", (f'%{args.project}%',))
        projects = cur.fetchall()
        if not projects:
            output({"success": False, "action": "record_distribution",
                    "error": f"未找到项目：{args.project}"})
            return
        if len(projects) > 1:
            output({"success": False, "action": "record_distribution",
                    "error": "匹配到多个项目，请提供更精确的项目名",
                    "matched_projects": [p['name'] for p in projects]})
            return

        project = projects[0]
        dist_date = args.date or date.today().isoformat()
        total = float(args.total)

        # 找目标收益记录
        if args.period:
            cur.execute("""
                SELECT * FROM pam_income_records
                WHERE project_id=%s AND period_label=%s
            """, (project['id'], args.period))
        else:
            cur.execute("""
                SELECT * FROM pam_income_records
                WHERE project_id=%s AND is_distributed=FALSE
                ORDER BY period_start DESC LIMIT 1
            """, (project['id'],))

        record = cur.fetchone()
        if not record:
            output({"success": False, "action": "record_distribution",
                    "error": f"未找到待分配的收益记录，请确认项目或指定 --period 参数"})
            return

        # 解析名单
        people = json.loads(args.list)

        # 更新收益记录状态
        cur.execute("""
            UPDATE pam_income_records
            SET is_distributed=TRUE, distributed_at=%s, distributed_amount=%s, updated_at=NOW()
            WHERE id=%s
        """, (dist_date, total, record['id']))

        # 批量插入明细
        for p in people:
            cur.execute("""
                INSERT INTO pam_distribution_details
                    (income_record_id, project_name, period_label, name, id_card, amount, bank_card, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (record['id'], project['name'], record['period_label'],
                  p['name'], p.get('id_card',''), p.get('amount',0),
                  p.get('bank_card',''), p.get('remark','')))
        conn.commit()

        output({
            "success": True,
            "action": "record_distribution",
            "project_name": project['name'],
            "period_label": record['period_label'],
            "dist_date": dist_date,
            "total_amount_wan": total,
            "person_count": len(people),
            "details": people
        })
    except Exception as e:
        conn.rollback()
        output({"success": False, "action": "record_distribution", "error": str(e)})
    finally:
        conn.close()


# ── 4. create_project ─────────────────────────────────────────────────────────
def action_create_project(args):
    """
    新建项目
    必填: --name 项目名称  --start 合同开始  --end 合同结束  --income 约定年收益(万元)
    可选: --villages 所属村(逗号分隔)  --content 建设内容  --investment 投资金额
          --operator 运营主体  --frequency year/half/quarter/month
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)

        villages = [v.strip() for v in args.villages.split(',')] if args.villages else []
        freq = args.frequency or 'year'

        cur.execute("""
            INSERT INTO pam_projects
                (name, villages, content, investment, operator,
                 contract_start, contract_end, agreed_income, income_frequency)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id, name
        """, (args.name, villages, args.content, args.investment,
              args.operator, args.start, args.end, args.income, freq))

        project_row = cur.fetchone()

        # 生成收益周期
        cur.execute("SELECT * FROM pam_projects WHERE id=%s", (project_row['id'],))
        project = cur.fetchone()
        periods_count = _generate_periods_for_project(cur, project)
        conn.commit()

        output({
            "success": True,
            "action": "create_project",
            "project_id": project_row['id'],
            "project_name": project_row['name'],
            "villages": villages,
            "contract_start": args.start,
            "contract_end": args.end,
            "agreed_income": float(args.income),
            "frequency": freq,
            "periods_generated": periods_count
        })
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        output({"success": False, "action": "create_project",
                "error": f"项目名称已存在：{args.name}"})
    except Exception as e:
        conn.rollback()
        output({"success": False, "action": "create_project", "error": str(e)})
    finally:
        conn.close()


# ── 5. query_projects ─────────────────────────────────────────────────────────
def action_query_projects(args):
    """查询所有项目及收益汇总"""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)
        cur.execute("""
            SELECT
                p.id, p.name, p.villages, p.operator,
                p.contract_start, p.contract_end,
                p.agreed_income, p.income_frequency,
                COUNT(r.id) AS period_count,
                COALESCE(SUM(CASE WHEN r.period_end <= CURRENT_DATE THEN r.due_amount END),0) AS due_total,
                COALESCE(SUM(r.paid_amount),0) AS paid_total,
                COALESCE(SUM(CASE WHEN r.period_end <= CURRENT_DATE THEN r.arrear_amount END),0) AS arrear_total
            FROM pam_projects p
            LEFT JOIN pam_income_records r ON r.project_id = p.id
            GROUP BY p.id
            ORDER BY p.name
        """)
        rows = [dict(r) for r in cur.fetchall()]
        output({"success": True, "action": "query_projects",
                "projects": rows, "count": len(rows)})
    except Exception as e:
        output({"success": False, "action": "query_projects", "error": str(e)})
    finally:
        conn.close()


# ── 6. query_income ──────────────────────────────────────────────────────────
def action_query_income(args):
    """
    查询某项目收益明细
    必填: --project 项目名关键词
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)
        cur.execute("SELECT * FROM pam_projects WHERE name LIKE %s", (f'%{args.project}%',))
        projects = cur.fetchall()
        if not projects:
            output({"success": False, "action": "query_income",
                    "error": f"未找到项目：{args.project}"})
            return

        results = []
        for p in projects:
            _generate_periods_for_project(cur, p)
            cur.execute("""
                SELECT period_label, period_start, period_end,
                       due_amount, paid_amount, arrear_amount,
                       is_distributed, distributed_at, distributed_amount, remark
                FROM pam_income_records
                WHERE project_id=%s ORDER BY period_start
            """, (p['id'],))
            records = [dict(r) for r in cur.fetchall()]
            results.append({"project_name": p['name'], "records": records})

        conn.commit()
        output({"success": True, "action": "query_income", "data": results})
    except Exception as e:
        output({"success": False, "action": "query_income", "error": str(e)})
    finally:
        conn.close()


# ── 7. query_distribution ────────────────────────────────────────────────────
def action_query_distribution(args):
    """
    查询分配到户明细
    必填: --project 项目名  可选: --period 周期标签
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        ensure_tables(cur)
        sql = """
            SELECT d.name, d.id_card, d.amount, d.bank_card, d.remark,
                   r.period_label, r.project_name, r.distributed_at
            FROM pam_distribution_details d
            JOIN pam_income_records r ON r.id = d.income_record_id
            WHERE r.project_name LIKE %s
        """
        params = [f'%{args.project}%']
        if args.period:
            sql += " AND r.period_label = %s"
            params.append(args.period)
        sql += " ORDER BY r.period_start, d.name"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        # 身份证脱敏
        for row in rows:
            ic = row.get('id_card', '')
            if len(ic) == 18:
                row['id_card'] = ic[:4] + '**********' + ic[-4:]
        output({"success": True, "action": "query_distribution",
                "records": rows, "count": len(rows)})
    except Exception as e:
        output({"success": False, "action": "query_distribution", "error": str(e)})
    finally:
        conn.close()


# ── 8. init_db ───────────────────────────────────────────────────────────────
def action_init_db(args):
    """初始化/检查数据库表结构"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        ensure_tables(cur)
        conn.commit()
        output({"success": True, "action": "init_db", "message": "数据库表结构初始化完成"})
    except Exception as e:
        conn.rollback()
        output({"success": False, "action": "init_db", "error": str(e)})
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="帮扶项目收益管理 CLI，所有输出为 JSON 格式"
    )
    sub = parser.add_subparsers(dest='action', required=True)

    # query_arrears
    sub.add_parser('query_arrears', help='查询拖欠情况')

    # record_payment
    p_pay = sub.add_parser('record_payment', help='录入缴款')
    p_pay.add_argument('--project', required=True, help='项目名关键词')
    p_pay.add_argument('--amount', required=True, type=float, help='缴款金额（万元）')
    p_pay.add_argument('--date', help='缴款日期 YYYY-MM-DD，默认今天')
    p_pay.add_argument('--period', help='指定周期标签（可选）')

    # record_distribution
    p_dist = sub.add_parser('record_distribution', help='记录分配到户')
    p_dist.add_argument('--project', required=True, help='项目名关键词')
    p_dist.add_argument('--total', required=True, type=float, help='到户总金额（万元）')
    p_dist.add_argument('--list', required=True, help='名单 JSON 字符串')
    p_dist.add_argument('--date', help='分配日期 YYYY-MM-DD，默认今天')
    p_dist.add_argument('--period', help='指定周期标签（可选）')

    # create_project
    p_create = sub.add_parser('create_project', help='新建项目')
    p_create.add_argument('--name', required=True, help='项目名称')
    p_create.add_argument('--start', required=True, help='合同开始日期 YYYY-MM-DD')
    p_create.add_argument('--end', required=True, help='合同结束日期 YYYY-MM-DD')
    p_create.add_argument('--income', required=True, type=float, help='约定年收益（万元）')
    p_create.add_argument('--villages', help='所属村，逗号分隔')
    p_create.add_argument('--content', help='建设内容')
    p_create.add_argument('--investment', type=float, help='投资金额（万元）')
    p_create.add_argument('--operator', help='运营主体')
    p_create.add_argument('--frequency', default='year',
                          choices=['year','half','quarter','month'], help='收益频率')

    # query_projects
    sub.add_parser('query_projects', help='查询所有项目汇总')

    # query_income
    p_inc = sub.add_parser('query_income', help='查询项目收益明细')
    p_inc.add_argument('--project', required=True, help='项目名关键词')

    # query_distribution
    p_qd = sub.add_parser('query_distribution', help='查询分配到户明细')
    p_qd.add_argument('--project', required=True, help='项目名关键词')
    p_qd.add_argument('--period', help='周期标签（可选）')

    # init_db
    sub.add_parser('init_db', help='初始化数据库表')

    args = parser.parse_args()
    action_map = {
        'query_arrears':       action_query_arrears,
        'record_payment':      action_record_payment,
        'record_distribution': action_record_distribution,
        'create_project':      action_create_project,
        'query_projects':      action_query_projects,
        'query_income':        action_query_income,
        'query_distribution':  action_query_distribution,
        'init_db':             action_init_db,
    }
    action_map[args.action](args)

if __name__ == '__main__':
    main()
