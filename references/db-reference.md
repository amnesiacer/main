# 数据库初始化与维护参考

## 完整建表 SQL

```sql
-- 启用扩展（如需要UUID）
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 项目合同表
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

-- 收益周期记录表
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

-- 分配到户明细表
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

-- 索引
CREATE INDEX IF NOT EXISTS idx_income_project ON pam_income_records(project_id);
CREATE INDEX IF NOT EXISTS idx_income_arrear ON pam_income_records(arrear_amount) WHERE arrear_amount > 0;
CREATE INDEX IF NOT EXISTS idx_dist_record ON pam_distribution_details(income_record_id);
```

## 收益周期生成逻辑（Python）

```python
from datetime import date
from dateutil.relativedelta import relativedelta

def generate_periods(project_id, project_name, contract_start, contract_end, 
                     agreed_income, frequency, cur):
    """
    frequency: year / half / quarter / month
    """
    delta_map = {
        'year':    relativedelta(years=1),
        'half':    relativedelta(months=6),
        'quarter': relativedelta(months=3),
        'month':   relativedelta(months=1),
    }
    count_map = {'year': 1, 'half': 2, 'quarter': 4, 'month': 12}
    
    label_funcs = {
        'year':    lambda s, e: f"{s.year}年度",
        'half':    lambda s, e: f"{s.year}年{'上' if s.month <= 6 else '下'}半年",
        'quarter': lambda s, e: f"{s.year}年第{(s.month-1)//3+1}季度",
        'month':   lambda s, e: f"{s.year}年{s.month:02d}月",
    }
    
    delta = delta_map[frequency]
    per_period_income = agreed_income / count_map[frequency]
    
    current_start = contract_start
    today = date.today()
    # 生成到今天之后一个周期，保证当前周期可见
    gen_until = min(contract_end, today + delta)
    
    inserted = 0
    while current_start <= gen_until:
        period_end = min(current_start + delta - relativedelta(days=1), contract_end)
        label = label_funcs[frequency](current_start, period_end)
        
        cur.execute("""
            INSERT INTO pam_income_records 
                (project_id, project_name, period_label, period_start, period_end, due_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, period_start) DO NOTHING
        """, (project_id, project_name, label, current_start, period_end, per_period_income))
        
        inserted += cur.rowcount
        current_start += delta
    
    return inserted
```

## 常用查询

### 查看所有项目汇总
```sql
SELECT 
    p.name AS 项目名称,
    array_to_string(p.villages, '、') AS 所属村,
    p.operator AS 运营主体,
    p.contract_start AS 合同开始,
    p.contract_end AS 合同结束,
    p.agreed_income AS 约定年收益_万元,
    COALESCE(SUM(r.due_amount), 0) AS 应缴总额,
    COALESCE(SUM(r.paid_amount), 0) AS 已缴总额,
    COALESCE(SUM(r.arrear_amount), 0) AS 拖欠总额
FROM pam_projects p
LEFT JOIN pam_income_records r ON r.project_id = p.id AND r.period_end <= CURRENT_DATE
GROUP BY p.id
ORDER BY p.name;
```

### 查看某项目收益明细
```sql
SELECT 
    period_label AS 周期,
    due_amount AS 应缴_万元,
    paid_amount AS 实缴_万元,
    arrear_amount AS 拖欠_万元,
    CASE WHEN is_distributed THEN '已分配' ELSE '未分配' END AS 分配状态,
    distributed_at AS 分配时间,
    distributed_amount AS 到户金额_万元
FROM pam_income_records
WHERE project_name LIKE '%项目名%'
ORDER BY period_start;
```

### 查看分配到户明细
```sql
SELECT 
    d.name AS 姓名,
    LEFT(d.id_card, 4) || '**********' || RIGHT(d.id_card, 4) AS 身份证,
    d.amount AS 分配金额_元,
    d.bank_card AS 银行卡号,
    d.remark AS 备注
FROM pam_distribution_details d
JOIN pam_income_records r ON r.id = d.income_record_id
WHERE r.project_name LIKE '%项目名%'
  AND r.period_label = '2024年上半年';
```
