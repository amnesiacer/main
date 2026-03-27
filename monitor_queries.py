#!/usr/bin/env python3
"""
监测对象信息表查询分析函数
"""
import psycopg2
from psycopg2.extras import RealDictCursor
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


def query_village_basic(village_name: str) -> Dict:
    """
    查询村基本情况：总户数、总人数
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 总户数（按户编号去重）
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s
    ''', (village_name,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "总户数": result[0],
        "总人数": result[1]
    }


def query_village_tuopinhu(village_name: str) -> Dict:
    """
    查询村脱贫户情况：户数、人数
    定义：户类型 = '脱贫户'
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s AND "户类型" = '脱贫户'
    ''', (village_name,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "脱贫户_户数": result[0],
        "脱贫户_人数": result[1]
    }


def query_village_jianceduixiang(village_name: str) -> Dict:
    """
    查询村监测对象情况：户数、人数
    定义：监测对象类别 IS NOT NULL AND 监测对象类别 != ''
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
    ''', (village_name,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "监测对象_户数": result[0],
        "监测对象_人数": result[1]
    }


def query_village_weixiaochu(village_name: str) -> Dict:
    """
    查询村未消除风险监测对象情况：户数、人数
    定义：监测对象类别 IS NOT NULL AND 监测对象类别 != '' AND 风险是否已消除 = '否'
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
        AND "风险是否已消除" = '否'
    ''', (village_name,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "未消除风险监测对象_户数": result[0],
        "未消除风险监测对象_人数": result[1]
    }


def query_village_weixiaochu_not_doudi(village_name: str) -> Dict:
    """
    查询村不是兜底户且未消除风险的监测对象情况：户数、人数
    定义：监测对象类别 IS NOT NULL AND 监测对象类别 != '' 
          AND 风险是否已消除 = '否' 
          AND (是否兜底保障户 IS NULL OR 是否兜底保障户 != '是')
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
        AND "风险是否已消除" = '否'
        AND ("是否兜底保障户" IS NULL OR "是否兜底保障户" != '是')
    ''', (village_name,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "非兜底未消除风险监测对象_户数": result[0],
        "非兜底未消除风险监测对象_人数": result[1]
    }


def query_village_all_stats(village_name: str) -> Dict:
    """
    查询村所有统计信息（综合查询）
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 总户数、总人数
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s
    ''', (village_name,))
    total = cursor.fetchone()
    
    # 2. 脱贫户
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s AND "户类型" = '脱贫户'
    ''', (village_name,))
    tuopin = cursor.fetchone()
    
    # 3. 监测对象
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
    ''', (village_name,))
    jiancedx = cursor.fetchone()
    
    # 4. 未消除风险监测对象
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
        AND "风险是否已消除" = '否'
    ''', (village_name,))
    weixiaochu = cursor.fetchone()
    
    # 5. 非兜底且未消除风险监测对象
    cursor.execute('''
        SELECT COUNT(DISTINCT "户编号") as 户数, COUNT(*) as 人数
        FROM "监测对象信息"
        WHERE "村" = %s 
        AND "监测对象类别" IS NOT NULL 
        AND "监测对象类别" != ''
        AND "风险是否已消除" = '否'
        AND ("是否兜底保障户" IS NULL OR "是否兜底保障户" != '是')
    ''', (village_name,))
    not_doudi = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return {
        "村名": village_name,
        "总户数": total[0],
        "总人数": total[1],
        "脱贫户_户数": tuopin[0],
        "脱贫户_人数": tuopin[1],
        "监测对象_户数": jiancedx[0],
        "监测对象_人数": jiancedx[1],
        "未消除风险监测对象_户数": weixiaochu[0],
        "未消除风险监测对象_人数": weixiaochu[1],
        "非兜底未消除风险监测对象_户数": not_doudi[0],
        "非兜底未消除风险监测对象_人数": not_doudi[1]
    }


def query_village_list() -> List[str]:
    """
    获取所有村名列表
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT "村" FROM "监测对象信息" ORDER BY "村"')
    villages = [row[0] for row in cursor.fetchall() if row[0]]
    
    cursor.close()
    conn.close()
    
    return villages


def query_all_villages_stats() -> List[Dict]:
    """
    查询所有村的统计信息
    """
    villages = query_village_list()
    results = []
    for village in villages:
        stats = query_village_all_stats(village)
        results.append(stats)
    return results


def print_village_report(village_name: str):
    """
    打印村的完整统计报告
    """
    stats = query_village_all_stats(village_name)
    
    print(f"\n{'='*50}")
    print(f"【{stats['村名']}】统计报告")
    print(f"{'='*50}")
    print(f"总户数：{stats['总户数']} 户")
    print(f"总人数：{stats['总人数']} 人")
    print(f"\n脱贫户：{stats['脱贫户_户数']} 户 / {stats['脱贫户_人数']} 人")
    print(f"监测对象：{stats['监测对象_户数']} 户 / {stats['监测对象_人数']} 人")
    print(f"未消除风险监测对象：{stats['未消除风险监测对象_户数']} 户 / {stats['未消除风险监测对象_人数']} 人")
    print(f"非兜底未消除风险监测对象：{stats['非兜底未消除风险监测对象_户数']} 户 / {stats['非兜底未消除风险监测对象_人数']} 人")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    # 测试：查询关庙村
    print_village_report("关庙村")
    
    # 也可以查询其他村
    # print_village_report("马东村")
