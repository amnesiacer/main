from monitor_queries import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT DISTINCT "户编号"
    FROM "监测对象信息"
    WHERE "监测对象类别" IS NOT NULL 
      AND "监测对象类别" != ''
      AND "乡" = '东宋镇'
    ORDER BY "户编号"
""")
rows = cur.fetchall()
for row in rows:
    print(row[0])
cur.close()
conn.close()
