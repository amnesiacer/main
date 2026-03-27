"""
收益周期生成工具

规则：
- 首次导入：生成从合同开始日到当年12月31日的所有周期
- 每年手动生成：用户调用 generate_year 指定年份，追加该年周期
- period_label 显示具体日期，如 2023.08.10-2024.08.09
- 已存在周期（project_id+period_start 唯一）自动跳过
"""
from datetime import date
from dateutil.relativedelta import relativedelta


FREQ_CONFIG = {
    "year":    dict(delta=relativedelta(years=1),  per_year=1),
    "half":    dict(delta=relativedelta(months=6), per_year=2),
    "quarter": dict(delta=relativedelta(months=3), per_year=4),
    "month":   dict(delta=relativedelta(months=1), per_year=12),
}


def make_label(period_start: date, period_end: date) -> str:
    """生成显示具体日期的周期标签，如 2023.08.10-2024.08.09"""
    return "{}.{:02d}.{:02d}-{}.{:02d}.{:02d}".format(
        period_start.year, period_start.month, period_start.day,
        period_end.year, period_end.month, period_end.day
    )


def generate_periods_until(cur, project_id: int, project_name: str,
                            contract_start: date, contract_end: date,
                            agreed_income: float, frequency: str,
                            until_date: date) -> int:
    """
    生成从 contract_start 到 until_date 之间的所有周期（不超过 contract_end）。
    返回新增条数。
    """
    cfg = FREQ_CONFIG.get(frequency, FREQ_CONFIG["year"])
    delta = cfg["delta"]
    per_period = round(float(agreed_income) / cfg["per_year"], 4)

    gen_end = min(contract_end, until_date)

    inserted = 0
    cur_start = contract_start
    while cur_start <= gen_end:
        period_end = min(cur_start + delta - relativedelta(days=1), contract_end)
        # 只有 period_start 在 gen_end 之前才生成
        if cur_start > gen_end:
            break
        label = make_label(cur_start, period_end)
        cur.execute("""
            INSERT INTO pam_income_records
                (project_id, project_name, period_label, period_start, period_end, due_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, period_start) DO NOTHING
        """, (project_id, project_name, label, cur_start, period_end, per_period))
        inserted += cur.rowcount
        cur_start += delta

    return inserted


def generate_periods_initial(cur, project_id: int, project_name: str,
                              contract_start: date, contract_end: date,
                              agreed_income: float, frequency: str) -> int:
    """首次导入：生成到当年12月31日"""
    current_year_end = date(date.today().year, 12, 31)
    return generate_periods_until(cur, project_id, project_name,
                                   contract_start, contract_end,
                                   agreed_income, frequency, current_year_end)


def generate_periods_for_year(cur, project_id: int, project_name: str,
                               contract_start: date, contract_end: date,
                               agreed_income: float, frequency: str,
                               year: int) -> int:
    """为指定年份生成周期"""
    year_end = date(year, 12, 31)
    return generate_periods_until(cur, project_id, project_name,
                                   contract_start, contract_end,
                                   agreed_income, frequency, year_end)


# 保持向后兼容的别名
generate_periods = generate_periods_initial
