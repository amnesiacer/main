# 长期记忆

## 看板模板化架构

**页面地址**: https://amnesiacer.github.io/main/skills/poverty-alleviation-mgmt/dashboard.html
**文件位置**: `skills/poverty-alleviation-mgmt/`

**更新流程**: 编辑 `dashboard_data.json` → 运行 `python3 generate_html.py` → `git push amnesiacer main`

| 文件 | 作用 |
|------|------|
| `dashboard_data.json` | 数据源（编辑这个） |
| `generate_html.py` | JSON → HTML 生成器 |
| `extract_data.py` | HTML → JSON 反向提取（备用） |
| `dashboard.html` | 自动生成，勿手动编辑 |

**规则**: 看板页面永远不要手动编辑，只通过 generate_html.py 从 JSON 生成。

## 马店镇光伏电站

- 7个村有光伏电站：关庙村、张村村、上窑村、小街村、太平庄村、田村村、东仇村
- 2025年光伏收益均已拨付到村
- 分配状态：小街村已分配到户；其余6个村（关庙村、张村村、上窑村、太平庄村、田村村、东仇村）尚未分配

## 监测对象数据库查询方法

### 数据库连接
- **类型:** PostgreSQL
- **地址:** www.amnesiac.cn:15432
- **数据库:** Mydates
- **表名:** 监测对象信息
- **覆盖范围:** 河南省洛阳市洛宁县 24 个村

### 查询核心要点

**统计逻辑：**
- 总户数 = `COUNT(DISTINCT 户编号)` —— 必须去重，同一户有多名家庭成员
- 总人数 = `COUNT(*)` —— 总记录数，每条记录代表一个人
- 脱贫户/监测对象需分别统计户数和人数

**关键字段条件：**
- 脱贫户: `户类型 = '脱贫户'`
- 监测对象: `监测对象类别 IS NOT NULL AND 监测对象类别 != ''`
- 未消除风险: `监测对象类别 IS NOT NULL AND 监测对象类别 != '' AND 风险是否已消除 = '否'`

### 标准查询 SQL

```sql
SELECT 
    村 as 行政村,
    COUNT(DISTINCT 户编号) as 总户数,
    COUNT(*) as 总人数,
    COUNT(DISTINCT CASE WHEN 户类型 = '脱贫户' THEN 户编号 END) as 脱贫户_户数,
    COUNT(CASE WHEN 户类型 = '脱贫户' THEN 1 END) as 脱贫户_人数,
    COUNT(DISTINCT CASE WHEN 监测对象类别 IS NOT NULL AND 监测对象类别 != '' THEN 户编号 END) as 监测对象_户数,
    COUNT(CASE WHEN 监测对象类别 IS NOT NULL AND 监测对象类别 != '' THEN 1 END) as 监测对象_人数,
    COUNT(DISTINCT CASE WHEN 监测对象类别 IS NOT NULL AND 监测对象类别 != '' AND 风险是否已消除 = '否' THEN 户编号 END) as 未消除风险_户数,
    COUNT(CASE WHEN 监测对象类别 IS NOT NULL AND 监测对象类别 != '' AND 风险是否已消除 = '否' THEN 1 END) as 未消除风险_人数
FROM 监测对象信息
GROUP BY 村
ORDER BY 村
```

### 数据特点
- 同一户编号对应多条记录（家庭成员）
- 例如：一户可能有户主、配偶、子女等多条记录
- 统计时务必区分户数和人数

### 注意事项
1. 每次查询必须直连数据库，禁用缓存
2. 户数统计必须 `DISTINCT`
3. 脱贫户/监测对象需同时输出户数和人数
