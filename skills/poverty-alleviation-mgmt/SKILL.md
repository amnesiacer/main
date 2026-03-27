---
name: poverty-alleviation-mgmt
description: 帮扶项目收益管理技能。用于管理帮扶项目（光伏电站、樱桃种植、集体经济等）的合同信息、收益记录和分配到户情况。当用户提到"帮扶项目"、"光伏电站"、"收益分配"、"拖欠收益"、"项目合同"、"到户金额"、"收益周期"、"缴纳收益"、"看板"等相关词汇时，必须触发此技能。
---

# 帮扶项目收益管理技能

## 工作流程（三步）

```
第一步：理解自然语言  →  第二步：调用 pam.py 脚本  →  第三步：解析JSON结果呈现给用户
```

**脚本路径**：`~/.openclaw/workspace/skills/poverty-alleviation-mgmt/scripts/`  
**调用方式**：`cd ~/.openclaw/workspace/skills/poverty-alleviation-mgmt/scripts && python3 pam.py <action> [参数...]`  
**返回格式**：统一 JSON → `{"status": "ok"|"error", "message": "...", "data": {...}}`

---

## 第一步：意图识别与参数提取

### 操作映射表

| 用户说 | action | 必须提取 | 可选提取 |
|---|---|---|---|
| 查拖欠、哪些项目欠钱 | `query_arrears` | — | — |
| 查项目、项目情况、有哪些项目 | `query_projects` | — | — |
| 查收益、收益情况、收益明细 | `query_income` | project | period |
| 查分配、分配明细 | `query_distribution` | project | period |
| 缴纳、已缴、付款了 | `record_payment` | project, amount | date, period |
| 分配到户、发放到户、分配完毕 | `record_distribution` | project, amount, list | date |
| 新建项目、录入合同 | `create_project` | name, contract_start, contract_end, agreed_income | 其他字段 |
| 生成XX年收益周期、新一年的周期 | `generate_year` | year | project |
| 生成看板、更新看板、查看看板 | `build_dashboard` | — | — |
| 初始化、建表 | `init` | — | — |

### 参数提取规则

- **project**：提取项目名关键词（如"光伏电站项目"→ `--project 光伏电站项目`）
- **amount**：统一转为万元（"12.5万元"→`12.5`，"125000元"→`12.5`）
- **date**：提到"今天"→今天日期 YYYY-MM-DD；未提及→不传（脚本默认今天）
- **period**：提到收益周期关键词时传入，否则不传（脚本自动取最早拖欠周期）
- **year**：提取四位年份数字
- **list**：解析名单为 JSON 数组（见格式说明）

### 名单解析格式

用户输入：`姓名 身份证号 金额(元) 银行卡号 [备注]`，每行一条。转为：
```json
[{"name":"张三","id_card":"111111111111111111","amount":895900,"bank_card":"1123416546"}]
```

---

## 第二步：调用脚本

### 完整命令速查

```bash
# 进入脚本目录（必须）
cd /home/claude/poverty-alleviation-mgmt/scripts

# 初始化数据库
python3 pam.py init

# 查询拖欠（仅已到期的收益，实时计算）
python3 pam.py query_arrears

# 查询所有项目汇总
python3 pam.py query_projects

# 查询某项目收益台账
python3 pam.py query_income --project 光伏电站项目
python3 pam.py query_income --project 光伏电站项目 --period 2023.08

# 查询分配到户明细
python3 pam.py query_distribution --project 光伏电站项目

# 录入缴款
python3 pam.py record_payment --project 光伏电站项目 --amount 12.5
python3 pam.py record_payment --project 光伏电站项目 --amount 12.5 --date 2025-03-26

# 录入分配到户（自动触发看板重建）
python3 pam.py record_distribution \
  --project 光伏电站项目 --amount 8.959 \
  --list '[{"name":"张三","id_card":"111111111111111111","amount":895900,"bank_card":"1123416546"}]'

# 新建项目（首次导入，自动生成到当年年底的收益周期）
python3 pam.py create_project --data '{
  "name":"光伏电站项目",
  "villages":["A村","B村"],
  "contract_start":"2023-08-10",
  "contract_end":"2033-08-09",
  "agreed_income":25.0,
  "income_frequency":"year",
  "operator":"XX能源公司",
  "investment":200.0
}'

# 每年手动生成新一年的收益周期
python3 pam.py generate_year --year 2026
python3 pam.py generate_year --year 2026 --project 光伏电站项目

# 生成可视化看板并推送 GitHub
python3 pam.py build_dashboard
```

---

## 第三步：解析结果并呈现

- `status == "error"` → 说明失败原因，提示修正方法
- `data.ambiguous == true` → 列出候选项目让用户确认
- `status == "ok"` → 按模板格式化输出

### 回复模板

**query_arrears**：
```
以下项目存在收益拖欠（截至今日，合同未到期收益不计入）：

| 项目名称 | 收益周期 | 应缴 | 已缴 | 拖欠 |
|---------|---------|------|------|------|
| ... | ... | ...万元 | ...万元 | ...万元 |

共 N 条拖欠记录，合计拖欠 X.XXXX 万元。
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
（看板已在后台自动更新）
```

**generate_year**：
```
✅ {year}年收益周期已生成
各项目新增情况：{results列表}
共新增 {total_new} 条周期记录
```

**build_dashboard**：
```
✅ 看板已生成
- 本地文件：{local_file}
- GitHub：{url 或失败原因}
- 数据概况：{stats}
```

---

## 收益周期说明

- **首次创建项目**：自动生成合同开始日 → 当年12月31日内的所有周期
- **每年1月**：用户说"生成2026年收益周期"，执行 `generate_year --year 2026`
- **周期标签格式**：`2023.08.10-2024.08.09`（具体到日）
- **拖欠计算**：只统计 `period_end <= 今天` 的记录，未到期收益不显示

## 看板 & GitHub 配置

- **推送方式**：SSH（`amnesiacer` GitHub 账户，自动完成，无需 token）
- **推送目标**：`amnesiacer/main` 仓库的 `index.html` + `dashboard.html`
- **自动触发**：`record_payment` 和 `record_distribution` 操作后静默触发看板重建+推送
- **手动触发**：`build_dashboard` 生成看板并自动推送到 GitHub
- **访问地址**：https://amnesiacer.github.io/main/

## 注意事项

- **合并显示**：看板中仅村名不同的同类项目会合并为一行，点击"展开明细"查看各村
- **身份证脱敏**：查询和看板中均自动脱敏（前4后4，中间10位为`**********`）
- **amount 单位**：CLI 参数统一传万元；分配名单中的 amount 传元
