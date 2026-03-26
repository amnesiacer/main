"""
收益周期生成工具
"""
from datetime import date
from dateutil.relativedelta import relativedelta


FREQ_CONFIG = {
    "year":    dict(delta=relativedelta(years=1),  per_year=1),
    "half":    dict(delta=relativedelta(months=6), per_year=2),
    "quarter": dict(delta=relativedelta(months=3), per_year=4),
    "month":   dict(delta=relativedelta(months=1), per_year=12),
}


def make_label(frequency: str, period_start: date, period_end: date) -> str:
    """生成带具体日期的周期标签，格式如 2023.8.10-2024.8.9"""
    def fmt(d: date) -> str:
        return f"{d.year}.{d.month}.{d.day}"
    return f"{fmt(period_start)}-{fmt(period_end)}"


def _end_of_year(d: date) -> date:
    """返回日期所在年的12月31日"""
    return date(d.year, 12, 31)


def generate_periods(cur, project_id: int, project_name: str,
                     contract_start: date, contract_end: date,
                     agreed_income: float, frequency: str,
                     until_year: int = None) -> int:
    """
    生成/补全收益周期，返回新增条数。
    已存在的周期（按 project_id+period_start 唯一）跳过。

    参数 until_year：
      - None 时（首次导入/默认）：生成到当年年底（12月31日），不超过合同结束日
      - 指定年份时：生成到该年12月31日（用于手动生成新年份）
    """
    cfg = FREQ_CONFIG.get(frequency, FREQ_CONFIG["year"])
    delta = cfg["delta"]
    per_period = round(float(agreed_income) / cfg["per_year"], 4)

    if until_year is not None:
        gen_until = min(contract_end, date(until_year, 12, 31))
    else:
        gen_until = min(contract_end, _end_of_year(date.today()))

    inserted = 0
    cur_start = contract_start
    while cur_start <= gen_until:
        period_end = min(cur_start + delta - relativedelta(days=1), contract_end)
        label = make_label(frequency, cur_start, period_end)

        cur.execute("""
            INSERT INTO pam_income_records
                (project_id, project_name, period_label, period_start, period_end, due_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, period_start) DO NOTHING
        """, (project_id, project_name, label, cur_start, period_end, per_period))
        inserted += cur.rowcount
        cur_start += delta

    return inserted
