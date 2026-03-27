#!/usr/bin/env python3
"""
监测对象信息表 - 自定义查询函数
用于务工、收入、风险等专项查询
"""
import psycopg2
from typing import Dict, List, Tuple, Optional

DB_CONFIG = {
    "host": "www.amnesiac.cn",
    "port": 15432,
    "database": "Mydates",
    "user": "amnesiac",
    "password": "52Xiaofang"
}


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


def query_village_work_outside_province(village_name: str, province: str = "河南省") -> Dict:
    """
    查询某村在指定省份之外务工的人数
    
    Args:
        village_name: 村名
        province: 省份名称（默认河南省）
    
    Returns:
        {
            "村名": str,
            "总务工人数": int,
            "省内务工": int,
            "省外务工": int,
            "省外占比": str,
            "省外去向": List[Tuple[省份, 人数]]
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 总务工人数
    cursor.execute('''
        SELECT COUNT(*) 
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "务工所在地" IS NOT NULL 
        AND "务工所在地" != '';
    ''', (village_name,))
    total_work = cursor.fetchone()[0]
    
    # 省内务工
    cursor.execute('''
        SELECT COUNT(*) 
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "务工所在地" LIKE %s;
    ''', (village_name, province + '%'))
    inside = cursor.fetchone()[0]
    
    # 省外务工
    cursor.execute('''
        SELECT COUNT(*) 
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "务工所在地" IS NOT NULL 
        AND "务工所在地" != ''
        AND "务工所在地" NOT LIKE %s;
    ''', (village_name, province + '%'))
    outside = cursor.fetchone()[0]
    
    # 省外去向分布
    like_pattern = province + '%'
    cursor.execute('''
        SELECT 
            CASE 
                WHEN "务工所在地" LIKE '江苏省%%' THEN '江苏省'
                WHEN "务工所在地" LIKE '浙江省%%' THEN '浙江省'
                WHEN "务工所在地" LIKE '广东省%%' THEN '广东省'
                WHEN "务工所在地" LIKE '上海市%%' THEN '上海市'
                WHEN "务工所在地" LIKE '北京市%%' THEN '北京市'
                WHEN "务工所在地" LIKE '山西省%%' THEN '山西省'
                WHEN "务工所在地" LIKE '湖北省%%' THEN '湖北省'
                WHEN "务工所在地" LIKE '安徽省%%' THEN '安徽省'
                WHEN "务工所在地" LIKE '新疆%%' THEN '新疆'
                WHEN "务工所在地" LIKE '山东省%%' THEN '山东省'
                WHEN "务工所在地" LIKE '河北省%%' THEN '河北省'
                WHEN "务工所在地" LIKE '陕西省%%' THEN '陕西省'
                WHEN "务工所在地" LIKE '四川省%%' THEN '四川省'
                ELSE '其他'
            END as 省份,
            COUNT(*) as 人数
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "务工所在地" IS NOT NULL 
        AND "务工所在地" != ''
        AND "务工所在地" NOT LIKE %s
        GROUP BY 省份
        ORDER BY 人数 DESC;
    ''', (village_name, like_pattern))
    provinces = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    percentage = f"{(outside/total_work*100):.1f}%" if total_work > 0 else "0%"
    
    return {
        "村名": village_name,
        "总务工人数": total_work,
        "省内务工": inside,
        "省外务工": outside,
        "省外占比": percentage,
        "省外去向": provinces
    }


def query_village_workers_detail(village_name: str, outside_province_only: bool = False, limit: int = 50) -> List[Dict]:
    """
    查询村务工人员详细信息
    
    Args:
        village_name: 村名
        outside_province_only: 是否只查省外务工
        limit: 返回记录数限制
    
    Returns:
        List[{
            "姓名": str,
            "务工所在地": str,
            "务工企业名称": str,
            "务工时间_月": int
        }]
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    sql = '''
        SELECT "姓名", "务工所在地", "务工企业名称", "务工时间（月）"
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "务工所在地" IS NOT NULL 
        AND "务工所在地" != ''
    '''
    params = [village_name]
    
    if outside_province_only:
        sql += ' AND "务工所在地" NOT LIKE \'河南省%\''
    
    sql += ' ORDER BY "务工所在地" LIMIT %s'
    params.append(limit)
    
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return [
        {
            "姓名": row[0],
            "务工所在地": row[1],
            "务工企业名称": row[2] or "",
            "务工时间_月": row[3]
        }
        for row in rows
    ]


def query_village_income_stats(village_name: str) -> Dict:
    """
    查询村收入统计
    
    Returns:
        {
            "村名": str,
            "人均纯收入_平均": float,
            "人均纯收入_中位数": float,
            "人均纯收入_最低": float,
            "人均纯收入_最高": float,
            "工资性收入_平均": float,
            "生产经营性收入_平均": float,
            "财产性收入_平均": float,
            "转移性收入_平均": float
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    fields = [
        "人均纯收入（元）",
        "工资性收入",
        "生产经营性收入",
        "财产性收入",
        "转移性收入"
    ]
    
    result = {"村名": village_name}
    
    for field in fields:
        cursor.execute(f'''
            SELECT 
                AVG("{field}"),
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY "{field}"),
                MIN("{field}"),
                MAX("{field}")
            FROM "监测对象信息"
            WHERE "村" = %s AND "{field}" IS NOT NULL
        ''', (village_name,))
        
        row = cursor.fetchone()
        key = field.replace("（元）", "").replace("收入", "_平均")
        result[f"{key}_平均"] = round(row[0], 2) if row[0] else 0
        if field == "人均纯收入（元）":
            result["人均纯收入_中位数"] = round(row[1], 2) if row[1] else 0
            result["人均纯收入_最低"] = round(row[2], 2) if row[2] else 0
            result["人均纯收入_最高"] = round(row[3], 2) if row[3] else 0
    
    cursor.close()
    conn.close()
    
    return result


def query_village_risk_analysis(village_name: str) -> Dict:
    """
    查询村风险分析（致贫/返贫风险）
    
    Returns:
        {
            "村名": str,
            "风险类型分布": List[Tuple[风险类型, 人数]],
            "风险消除情况": {
                "已消除": int,
                "未消除": int
            }
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 风险类型分布
    cursor.execute('''
        SELECT "致贫返贫风险", COUNT(*) 
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
        AND "致贫返贫风险" IS NOT NULL
        AND "致贫返贫风险" != ''
        GROUP BY "致贫返贫风险"
        ORDER BY COUNT(*) DESC;
    ''', (village_name,))
    risk_types = cursor.fetchall()
    
    # 风险消除情况
    cursor.execute('''
        SELECT "风险是否已消除", COUNT(*) 
        FROM "监测对象信息" 
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
        GROUP BY "风险是否已消除";
    ''', (village_name,))
    risk_status = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    status_dict = {row[0]: row[1] for row in risk_status}
    
    return {
        "村名": village_name,
        "风险类型分布": risk_types,
        "风险消除情况": {
            "已消除": status_dict.get('是', 0),
            "未消除": status_dict.get('否', 0)
        }
    }


def query_village_age_structure(village_name: str) -> Dict:
    """
    查询村年龄结构
    
    Returns:
        {
            "村名": str,
            "年龄段分布": {
                "0-17岁": int,
                "18-35岁": int,
                "36-59岁": int,
                "60岁及以上": int
            }
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            SUM(CASE WHEN "年龄" < 18 THEN 1 ELSE 0 END) as 未成年,
            SUM(CASE WHEN "年龄" >= 18 AND "年龄" < 36 THEN 1 ELSE 0 END) as 青年,
            SUM(CASE WHEN "年龄" >= 36 AND "年龄" < 60 THEN 1 ELSE 0 END) as 中年,
            SUM(CASE WHEN "年龄" >= 60 THEN 1 ELSE 0 END) as 老年
        FROM "监测对象信息"
        WHERE "村" = %s AND "年龄" IS NOT NULL;
    ''', (village_name,))
    
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "年龄段分布": {
            "0-17岁": row[0] or 0,
            "18-35岁": row[1] or 0,
            "36-59岁": row[2] or 0,
            "60岁及以上": row[3] or 0
        }
    }


# 便捷函数：打印格式化报告

def print_work_report(village_name: str):
    """打印务工情况报告"""
    stats = query_village_work_outside_province(village_name)
    
    print(f"\n{'='*60}")
    print(f"【{stats['村名']}】务工情况报告")
    print(f"{'='*60}")
    print(f"总务工人数：{stats['总务工人数']} 人")
    print(f"河南省内务工：{stats['省内务工']} 人")
    print(f"河南省外务工：{stats['省外务工']} 人 ({stats['省外占比']})")
    print(f"\n省外务工去向分布：")
    for prov, count in stats['省外去向']:
        print(f"  {prov}: {count} 人")
    print(f"{'='*60}\n")


def print_income_report(village_name: str):
    """打印收入情况报告"""
    stats = query_village_income_stats(village_name)
    
    print(f"\n{'='*60}")
    print(f"【{stats['村名']}】收入情况报告")
    print(f"{'='*60}")
    print(f"人均纯收入：")
    print(f"  平均值：{stats['人均纯收入_平均']:.2f} 元")
    print(f"  中位数：{stats['人均纯收入_中位数']:.2f} 元")
    print(f"  最低值：{stats['人均纯收入_最低']:.2f} 元")
    print(f"  最高值：{stats['人均纯收入_最高']:.2f} 元")
    print(f"\n收入构成（平均）：")
    print(f"  工资性收入：{stats['工资性_平均']:.2f} 元")
    print(f"  生产经营性收入：{stats['生产经营性_平均']:.2f} 元")
    print(f"  财产性收入：{stats['财产性_平均']:.2f} 元")
    print(f"  转移性收入：{stats['转移性_平均']:.2f} 元")
    print(f"{'='*60}\n")


def print_risk_report(village_name: str):
    """打印风险分析报告"""
    stats = query_village_risk_analysis(village_name)
    
    print(f"\n{'='*60}")
    print(f"【{stats['村名']}】风险分析报告")
    print(f"{'='*60}")
    print(f"风险消除情况：")
    print(f"  已消除：{stats['风险消除情况']['已消除']} 人")
    print(f"  未消除：{stats['风险消除情况']['未消除']} 人")
    print(f"\n风险类型分布：")
    for risk_type, count in stats['风险类型分布']:
        print(f"  {risk_type}: {count} 人")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # 测试
    print_work_report("关庙村")
    print_income_report("关庙村")
    print_risk_report("石门村")
