---
name: railway-pdf-renamer
description: 铁路电子客票PDF批量重命名工具。从12306铁路电子发票PDF中自动提取乘车日期、出发站、到达站、票价金额，并按日期-出发地-目的地-金额格式批量重命名。当用户需要重命名铁路客票PDF、整理火车票发票、或从铁路电子客票中提取行程信息时触发此技能。支持处理字体描述符异常的PDF文件。
agent_created: true
---

# Railway PDF Renamer - 铁路电子客票PDF批量重命名

## Overview

从12306铁路电子客票PDF中自动提取日期、出发地、目的地、金额，按指定格式批量重命名。
内置字体描述符异常的fallback处理方案，可处理所有铁路电子客票PDF。

## 触发场景

- 用户要求重命名铁路客票/火车票PDF文件
- 用户要求从铁路电子发票中提取行程信息（日期、出发地、目的地、金额）
- 用户要求按"日期-出发地-目的地-金额"格式整理火车票PDF
- 用户提供了包含铁路电子客票PDF的文件夹并要求整理

## 工作流程

### Step 1: 确认参数

确认以下信息：
- **文件夹路径**: PDF文件所在文件夹（必填）
- **命名格式**: 默认 `{date}-{from}-{to}-{amount}`，用户可自定义
  - 可用变量: `{date}`, `{from}`, `{to}`, `{amount}`, `{train}`
  - 示例: `{date}-{from}-{to}-{amount}` → `20260511-北京南-泰安-242.pdf`
- **是否预览**: 建议先用 `--dry-run` 预览结果，确认无误后再执行

### Step 2: 执行重命名

运行脚本完成批量重命名:

```bash
python scripts/rename_railway_pdfs.py "文件夹路径" --dry-run
```

预览确认后，去掉 `--dry-run` 正式执行:

```bash
python scripts/rename_railway_pdfs.py "文件夹路径"
```

自定义命名格式:

```bash
python scripts/rename_railway_pdfs.py "文件夹路径" --format "{date}_{from}_{to}_{amount}"
```

### Step 3: 确认结果

执行后脚本会打印每个文件的重命名结果，确认所有文件重命名成功。

## 技术细节

### PDF文本提取

铁路电子客票PDF有两种情况:

1. **标准PDF** (大部分文件): 直接使用 `pypdf` 的 `page.extract_text()` 提取文本
2. **字体描述符异常PDF** (部分文件): 字体描述符同时包含 `/FontFile2` 和 `/FontFile3`，
   导致 pypdf 抛出 `"More than one /FontFile found"` 错误。
   Fallback方案: 直接解析 ContentStream，用 GBK 解码文本操作符中的原始字节

### 信息提取规则

| 字段 | 正则模式 | 示例 |
|------|---------|------|
| 日期 | `(\d{4})\s*年\s*(\d{2})\s*月\s*(\d{2})\s*日` | `2026年05月11日` → `20260511` |
| 金额 | `票价\s*[:：]\s*[￥¥]?\s*([\d.]+)` | `票价: ￥ 242.00` → `242` |
| 出发地 | 文本中最后两个 `XX站` 中的第一个 | `北京南站泰安站` → `北京南` |
| 目的地 | 文本中最后两个 `XX站` 中的第二个 | `北京南站泰安站` → `泰安` |

### 依赖

- Python 3.8+
- `pypdf` 库 (`pip install pypdf`)

## 资源

### scripts/

- `rename_railway_pdfs.py` - 核心脚本，支持命令行参数、dry-run预览、自定义命名格式
