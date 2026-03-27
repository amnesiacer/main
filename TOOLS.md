# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

## PostgreSQL 数据库 - 监测对象信息

**连接信息：**
```
postgresql://amnesiac:52Xiaofang@www.amnesiac.cn:15432/Mydates
```

**数据表：** `监测对象信息`（5157 条记录，200+ 字段）
- 覆盖：河南省洛阳市洛宁县 24 个村
- 数据类型：精准扶贫/乡村振兴监测数据

### 常用查询脚本

| 脚本 | 路径 | 用途 |
|------|------|------|
| 村统计查询 | `monitor_queries.py` | 户数、人数、脱贫户、监测对象等统计 |
| 自定义查询 | `custom_queries.py` | 务工、收入、风险等专项查询 |

### 快速查询命令

```bash
# 查看村统计报告
cd ~/.openclaw/workspace && python3 -c "from monitor_queries import print_village_report; print_village_report('关庙村')"

# 查看所有村列表
cd ~/.openclaw/workspace && python3 -c "from monitor_queries import query_village_list; print(query_village_list())"

# 查看所有村统计
cd ~/.openclaw/workspace && python3 -c "from monitor_queries import query_all_villages_stats; import json; [print(json.dumps(s, ensure_ascii=False)) for s in query_all_villages_stats()]"
```

### 关键字段定义

- **脱贫户**：户类型 = '脱贫户'
- **监测对象**：监测对象类别 IS NOT NULL AND 监测对象类别 != ''
- **未消除风险监测对象**：监测对象 + 风险是否已消除 = '否'
- **兜底户**：是否兜底保障户 = '是'

---

Add whatever helps you do your job. This is your cheat sheet.
