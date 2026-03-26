---
name: poverty-alleviation-mgmt
description: 帮扶项目收益管理技能。用于管理帮扶项目（光伏电站、樱桃种植、集体经济等）的合同信息、收益记录和分配到户情况。当用户提到"帮扶项目"、"光伏电站"、"收益分配"、"拖欠收益"、"项目合同"、"到户金额"、"收益周期"、"缴纳收益"等相关词汇时，必须触发此技能。
---

# 帮扶项目收益管理技能

## 工作流程（三步）

```
第一步：理解自然语言  →  第二步：调用 pam.py 脚本  →  第三步：解析JSON结果呈现给用户
```

**脚本路径**：`~/.openclaw/extensions/openclaw-lark/skills/poverty-alleviation-mgmt/scripts/pam.py`（或用户部署路径）
**调用方式**：`cd ~/.openclaw/extensions/openclaw-lark/skills/poverty-alleviation-mgmt/scripts && python3 pam.py <action> [参数...]`
**返回格式**：统一 JSON → `{"status": "ok"|"error", "message": "...", "data": {...}}`

---

## 第一步：意图识别与参数提取

### 操作映射表

| 用户说 | action | 必须提取 | 可选提取 |
|---|---|---|---|
| 查拖欠、哪些项目欠钱 | `query_arrears` | — | — |
| 查项目、项目情况、有哪些项目 | `query_projects` | — | — |
| 查收益、收益情况 | `query_income` | project | period |
| 查分配、分配明细 | `query_distribution` | project | period |
| 缴纳、已缴、付款了 | `record_payment` | project, amount | date, period |
| 分配到户、发放到户、分配完毕 | `record_distribution` | project, amount, list | date |
| 新建项目、录入合同 | `create_project` | name, contract_start, contract_end, agreed_income | 其他字段 |
| 生成收益周期、刷新周期 | `generate_periods_year` / `refresh_periods` | year（generate 时） | project |
| 生成可视化页面、导出看板 | `export_html` | — | — |
| 初始化、建表 | `init` | — | — |

### 参数提取规则

- **project**：提取项目名关键词（如"光伏电站项目"→ `--project 光伏电站项目`）
- **amount**：统一转为万元（"12.5万元"→`12.5`，"125000元"→`12.5`）
- **date**：提到"今天"→今天日期 YYYY-MM-DD；未提及→不传（脚本默认今天）
- **period**：提到周期词如"上半年"、"第1季度"→传入，否则不传
- **list**：解析名单为 JSON 数组（见格式说明）

### 名单解析格式

用户输入：`姓名 身份证号 金额(元) 银行卡号 [备注]`，每行一条。

转为 JSON：
```json
[
  {"name":"张三","id_card":"111111111111111111","amount":895900,"bank_card":"1123416546"},
  {"name":"李四","id_card":"222222222222222222","amount":500000,"bank_card":"9876543210"}
]
```

---

## 第二步：调用脚本

工作目录为脚本所在目录：
`cd ~/.openclaw/extensions/openclaw-lark/skills/poverty-alleviation-mgmt/scripts && python3 pam.py ...`

### 命令速查

```bash
# 查询拖欠
python3 pam.py query_arrears

# 查询所有项目汇总
python3 pam.py query_projects

# 查询某项目收益明细
python3 pam.py query_income --project 光伏电站项目
python3 pam.py query_income --project 光伏电站项目 --period 2024年上半年

# 查询分配到户明细
python3 pam.py query_distribution --project 光伏电站项目

# 录入缴款
python3 pam.py record_payment --project 光伏电站项目 --amount 12.5
python3 pam.py record_payment --project 光伏电站项目 --amount 12.5 --date 2025-03-26

# 录入分配到户
python3 pam.py record_distribution \
  --project 光伏电站项目 \
  --amount 8.959 \
  --list '[{"name":"张三","id_card":"111111111111111111","amount":895900,"bank_card":"1123416546"}]'

# 新建项目（--data 传 JSON 字符串）
python3 pam.py create_project --data '{"name":"光伏电站项目","villages":["A村","B村"],"contract_start":"2023-01-01","contract_end":"2033-12-31","agreed_income":5.0,"income_frequency":"half","operator":"XX能源公司","investment":80.0}'

# 手动生成指定年份收益周期
python3 pam.py generate_periods_year --year 2026
python3 pam.py generate_periods_year --year 2026 --project 光伏电站项目

# 刷新所有收益周期
python3 pam.py refresh_periods

# 导出可视化查询页面
python3 pam.py export_html

# 初始化数据库（首次使用）
python3 pam.py init
```

---

## 第三步：解析结果并呈现

收到 JSON 后：
- `status == "error"` → 向用户说明失败原因，提示如何修正
- `data.ambiguous == true` → 列出候选项目让用户确认
- `status == "ok"` → 按模板格式化输出

### 回复模板

**query_arrears**：
```
以下项目存在收益拖欠（截至今日）：

| 项目名称 | 收益周期 | 应缴 | 已缴 | 拖欠 |
|---------|---------|------|------|------|
| ... | yyyy.mm.dd| ...万元 | ...万元 | ...万元 |

共 N 条拖欠记录，合计拖欠 X.XX 万元。
```

**record_payment**：
```
✅ 缴款记录成功
- 项目：{project} | 周期：{period} | 日期：{payment_date}
- 本次缴款：{this_payment}万元
- 应缴：{due_amount}万元 | 已缴：{paid_amount}万元 | 拖欠：{arrear_amount}万元
- 状态：✅ 该周期已结清  /  ⚠️ 仍有拖欠
```

**record_distribution**：
```
✅ 分配到户记录成功
- 项目：{project} | 周期：{period} | 日期：{distributed_at}
- 到户总金额：{total_amount}万元 | 分配户数：{household_count}户
```

**create_project**：
```
✅ 项目"{name}"创建成功，已自动生成 {periods_generated} 个收益周期记录
```

---

## 注意事项

- **身份证脱敏**：脚本返回已脱敏（中间8位为`**`），直接展示
- **收益周期**：首次导入自动生成到当年年底（12月31日），之后每年需手动生成：`generate_periods_year --year 2026`
- **周期标签**：显示具体日期如 `2023.8.10-2024.8.9`，不再显示"2024年度"
- **字段缺失**：create_project 时若用户未提供必填字段，先收集完整再调用
- **单位说明**：amount 参数统一传万元；名单中分配金额传元（脚本内部处理换算）
- **可视化页面**：`export_html` 生成静态 HTML 文件，包含项目概览、收益明细、拖欠明细三个看板页，支持筛选搜索
- **项目合并显示**：仪表板中仅村名前缀不同、项目类型相同的项目必须合并为一行显示（如"上窑村光伏电站项目"+"关庙村光伏电站项目"→"光伏电站项目"）。合并规则：去掉"某某村"前缀后名称相同的项目归为一组。注意金额必须一致才可合并（如"20万元集体经济项目"和"70万元集体经济项目"不可合并）。合并逻辑在 `groupSimilarProjects()` 中实现，子项目名称以 `sub_projects` 字段存储；`getMergedName` 负责收入记录的项目名映射，点击项目卡片时 `viewProject` 需使用合并名称过滤。
