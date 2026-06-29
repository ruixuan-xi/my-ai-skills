---
title: "Video to Yingdao RPA Requirements Document"
summary: "Given a screen recording video, extract key frames, analyze the workflow, and generate a Word document matching the Yingdao (影刀) RPA requirements template."
agent_created: true
---

# Video → 影刀 RPA 需求文档

这个 skill 用于将用户提供的**操作录屏/演示视频**自动整理为符合**影刀 RPA 落地需求文档模板**的 Word 文档，包含流程说明、涉及系统、详细步骤截图与补充说明。

## 触发场景

- 用户说：「把这个视频整理成需求文档」
- 用户说：「按影刀模板生成文档」
- 用户给出一个视频文件路径并提到需求文档/Word/影刀/RPA

## 前置要求

执行此 skill 前，请确保 Python 环境已安装以下依赖：

```bash
pip install opencv-python python-docx pillow
```

如果当前环境没有 OpenCV，优先使用系统 Python（如 Python 3.11）或安装 `opencv-python-headless`。

## 处理流程

### 1. 接收输入

需要确认/获取以下信息：

| 输入项 | 说明 | 默认值 |
|--------|------|--------|
| `video_path` | 输入视频文件路径 | 用户指定 |
| `template_path` | 影刀需求模板 docx 路径 | `C:/Users/13251/.workbuddy/skills/video-to-rpa-doc/references/影刀RPA需求文档模板.docx` |
| `output_dir` | 中间帧和最终文档输出目录 | 当前 workspace 目录 |
| `title` | 封面标题 | 从视频内容推断 |
| `subtitle` | 封面副标题 | 可为空 |

### 2. 提取关键帧

使用 skill 中的脚本提取视频关键帧：

```bash
python ~/.workbuddy/skills/video-to-rpa-doc/scripts/extract_frames.py \
    <video_path> \
    <output_dir>/video_frames \
    --threshold 30 \
    --min-interval 1.0 \
    --frame-skip 5
```

脚本基于 OpenCV 的帧间 MSE 检测场景切换，适合屏幕录制类视频。

**参数调整建议：**
- 如果视频很长且变化慢：`--min-interval 2.0`
- 如果视频短且切换频繁：`--min-interval 0.5`
- 如果帧数太多：`--frame-skip 10`

### 3. 分析关键帧

按时间顺序查看提取出的 PNG 帧，理解视频展示的业务流程：

1. 识别流程起点、终点
2. 识别每个操作步骤的界面变化
3. 记录涉及的应用/App、系统类型、是否需要登录/验证码
4. 为每个关键步骤选择最具代表性的 1 张截图
5. 总结每个步骤的：名称、详细操作说明、补充说明

### 4. 构造生成配置

在输出目录创建 `config.json`，结构如下：

```json
{
    "template_path": "C:/Users/13251/.workbuddy/skills/video-to-rpa-doc/references/影刀RPA需求文档模板.docx",
    "output_path": "<output_dir>/需求文档.docx",
    "frames_dir": "<output_dir>/video_frames",
    "title": "iOS快捷指令：工时记录自动同步到日历",
    "subtitle": "",
    "version": "Version 1.0",
    "date": "auto",
    "basic_info": {
        "name": "流程名称",
        "department": "部门/适用对象",
        "description": "流程主题场景描述",
        "duration": "单次操作时间（如10秒）",
        "daily_count": "每天重复量（次）",
        "remarks": "备注说明"
    },
    "systems": [
        ["系统名称", "内部/外部", "iOS/Web/Windows", "No", "No", "无", "备注"]
    ],
    "steps": [
        {
            "name": "启动快捷指令",
            "desc": "详细操作说明，支持\\n换行。",
            "supplement": "补充说明及资料",
            "img": "frame_00_5s.png",
            "img_w": 5
        }
    ]
}
```

**字段说明：**
- `date`: 设为 `"auto"` 自动生成 `YYYY.MM.DD`
- `subtitle`: 如果不需要副标题，设为空字符串，脚本会清空副标题段落
- `systems`: 只列被集成的外部系统，**不要包含"影刀RPA"本身**（影刀是编排工具，不是被集成系统）
- `img`: 截图文件名（相对于 `frames_dir`）
- `img_w`: 截图宽度（cm），推荐 4~5.5

### 5. 生成 Word 文档

使用 skill 中的脚本生成最终文档：

```bash
python ~/.workbuddy/skills/video-to-rpa-doc/scripts/gen_doc.py <output_dir>/config.json
```

脚本会：
- 复制模板文件到输出路径
- 替换封面 3 个浮动文本框：标题、副标题、版本+日期（影刀RPA logo 和装饰线保持不动）
- 填写「流程基本信息」表
- 填写「应用系统」表并删除多余空行（**影刀RPA 不在系统列表中**）
- 填写「详细步骤解析」表，每步2行：**蓝色行第一列显示步骤名称**，白色行第一列显示描述、第二列插入截图（**无空行**）、第三列补充说明。表头自动修正为「步骤名称及详细说明 | 截图 | 其他补充说明及资料」，并删除多余空行
- **自动删除文档末尾因模板结构产生的空白页**（包括空白段落、lastRenderedPageBreak、页面分隔符等）

### 6. 用 Draw.io 生成流程图

Word 文档生成后，使用 **drawio** skill 自动生成可编辑的 Draw.io 业务流程图。

**流程图命名规则：**
- 文件名：`{title}流程图.drawio`（例如「短视频号信息采集流程图.drawio」）
- 存放在 `./diagrams/` 目录下
- 同时导出 PNG 到 `./diagrams/{title}流程图.png`

**生成流程：**

1. **调用 drawio skill**：根据 config.json 中的 steps 自动构建流程图
2. **构造流程图 XML**：使用 drawio 的 flowchart 模板，包含：
   - 开始/结束节点用圆角椭圆（`shape=ellipse`）
   - 操作步骤用圆角矩形（`rounded=1`）
   - 判断节点用菱形（`shape=rhombus`）
   - 配色简洁统一：节点浅蓝/浅绿背景，深色边框
3. **保存 .drawio 文件** 到 `./diagrams/` 目录
4. **导出 PNG 图片**（需 draw.io 桌面版 CLI；若无则提示用户手动导出）
5. **展示结果**：`present_files` 同时展示 .drawio 和 .png 文件

**Draw.io 流程图示例结构：**
```
开始(椭圆) → 步骤1(圆角矩形) → 步骤2(圆角矩形) → 判断条件(菱形)
  → 是：继续
  → 否：返回步骤1
→ 结束(椭圆)
```

### 7. 输出与确认

生成完成后：
1. 使用 `present_files` 展示最终 Word 文档 + 流程图（.drawio 和 .png）
2. **必须在回复中明确告知用户 Word 文档的完整绝对路径**，示例如下：
   > 📄 需求文档已保存到：**`C:/Users/13251/WorkBuddy/2026-06-23-20-45-29/XXX-需求文档.docx`**
   
   路径从 `config.json` 的 `output_path` 字段获取，严禁省略或使用相对路径。
3. 简要说明文档结构和关键内容
4. 告知流程图文件位置（.drawio 可用 draw.io 网页版或桌面版打开编辑，.png 可直接查看）
5. 询问用户是否需要调整：标题、步骤数量、截图选择、配色方案、文字描述等

## 模板说明

标准模板位置：

`C:/Users/13251/.workbuddy/skills/video-to-rpa-doc/references/影刀RPA需求文档模板.docx`

模板特点：
- 基于 `生产入库单自动写入金蝶对应字段-需求详情表` 同款样式
- 2 节 A4 页面（21cm × 29.7cm），所有页面带统一页边框
- 封面使用浮动文本框（WPS textbox）呈现标题、副标题、版本与日期；影刀RPA logo 为浮动形状内嵌
- 包含 3 个标准表格：流程基本信息、应用系统、详细步骤解析
- 详细步骤解析表预留 10 个步骤（21 行）

## 常见问题

**Q: 封面和第二页纸张大小不一样？**
A: 标准模板已统一为 2 节 A4（21cm × 29.7cm），所有页面尺寸一致。

**Q: 影刀 RPA logo 会丢失吗？**
A: 模板封面已内嵌影刀 RPA logo（浮动形状），脚本只修改文字文本框，不会影响 logo 和装饰线。

**Q: 副标题不需要？**
A: 在 config.json 中把 `subtitle` 设为空字符串，脚本会清空该段落。

**Q: 应用系统表底部有多余空行？**
A: 脚本会根据 `systems` 数量自动删除多余行，只保留表头 + 实际数据行。

**Q: 文档末尾出现空白页？**
A: gen_doc.py 现在会自动删除末尾空白段落和 lastRenderedPageBreak。如果仍有问题，检查模板是否包含额外的 section break。

**Q: 步骤名称没有出现在蓝色行？**
A: gen_doc.py 现在会自动将步骤名称（`step.name`）填入蓝色行的第一列（col 0），蓝色行显示步骤名称，白色行仅显示详细描述。

**Q: 步骤表模板只有10个步骤占位，实际步骤超过10个？**
A: 当前脚本依赖模板已有足够的占位行。如果步骤超过10个，需要先在模板中追加足够行数，或提示用户精简步骤。

## 脚本文件

- `scripts/extract_frames.py`: 视频关键帧提取
- `scripts/gen_doc.py`: 根据 JSON 配置生成 Word 文档
- `references/影刀RPA需求文档模板.docx`: 标准 Word 模板
- `references/yingdao_logo.jpeg`: 封面页影刀 RPA logo
- `references/template_structure.md`: 模板结构说明
