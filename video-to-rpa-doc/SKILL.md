---
title: "Video to Yingdao RPA Requirements Document"
summary: "Given a screen recording video, extract audio for ASR transcription (via 影刀 AI Work OS), extract key frames, analyze the workflow, and generate a Word document matching the Yingdao (影刀) RPA requirements template."
agent_created: true
---

# Video → 影刀 RPA 需求文档

这个 skill 用于将用户提供的**操作录屏/演示视频**自动整理为符合**影刀 RPA 落地需求文档模板**的 Word 文档。支持**先听音频转录为文字**（影刀 AI Work OS ASR），**再看画面分析操作步骤**，两者互补生成更精准的需求文档。

## 触发场景

- 用户说：「把这个视频整理成需求文档」
- 用户说：「按影刀模板生成文档」
- 用户给出一个视频文件路径并提到需求文档/Word/影刀/RPA

## 前置要求

### Python 依赖

执行此 skill 前，请确保 Python 环境已安装以下依赖：

```bash
pip install opencv-python python-docx pillow imageio-ffmpeg requests
```

> **imageio-ffmpeg** 提供内置便携版 ffmpeg（用于音频提取），如 PyPI 下载慢可换清华源：
> ```bash
> pip install -i https://pypi.tuna.tsinghua.edu.cn/simple imageio-ffmpeg
> ```

如果当前环境没有 OpenCV，优先使用系统 Python（如 Python 3.11）或安装 `opencv-python-headless`。

### 影刀 API 凭证

ASR 转录依赖影刀 AI Work OS 的语音识别工作流，需提前设置以下环境变量：

| 环境变量 | 说明 |
|----------|------|
| `YINGDAO_AUTH_TOKEN` | 影刀 API 认证 Token |
| `YINGDAO_WORKFLOW_ID` | 影刀 ASR 工作流 ID |

> 如未设置，运行 ASR 脚本时会提示并退出。请勿将凭证写入脚本或文档中。

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

### 2. 提取音频并转录（新增 ⭐）

> **必须先执行此步骤**：音频旁白通常包含比画面更丰富的流程细节和业务逻辑。

**2a. 提取音频：**

```bash
python ~/.workbuddy/skills/video-to-rpa-doc/scripts/extract_audio.py \
    <video_path> \
    --output <output_dir>/video_audio.wav \
    --rate 16000
```

需要 `imageio-ffmpeg` 包（内置便携版 ffmpeg，无需系统安装）。如未安装：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple imageio-ffmpeg
```

**2b. 语音转文字（影刀 AI Work OS ASR 工作流）：**

```bash
python ~/.workbuddy/skills/video-to-rpa-doc/scripts/asr_transcribe.py \
    <output_dir>/video_audio.wav \
    --output <output_dir>/video_transcript.txt
```

调用影刀 AI Work OS 的语音识别工作流，返回带时间戳的完整转录文本。需要提前设置环境变量 `YINGDAO_AUTH_TOKEN` 和 `YINGDAO_WORKFLOW_ID`。

**2c. 阅读转录文本，提取关键信息：**

- 流程的 6W（What/Why/Who/When/Where/How）
- 每个步骤的详细操作说明（旁白比画面更详尽）
- 涉及的系统名称、登录方式、注意事项
- AI 核对规则、字段映射关系等业务逻辑细节

> 转录文本与画面截图应**互补对照**：画面看界面操作，音频听业务解释。

### 3. 提取关键帧

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

### 4. 分析关键帧（结合音频转录）

按时间顺序查看提取出的 PNG 帧，**同时参考音频转录文本**，综合理解视频展示的业务流程：

1. 先阅读音频转录文本（`video_transcript.txt`），掌握视频的总体结构和旁白讲解的业务逻辑
2. 再按时间顺序查看 PNG 帧，识别每个操作步骤对应的界面变化
3. 将转录文本中的操作描述与截图画面进行对照：画面确认界面元素，音频补充操作细节
4. 识别流程起点、终点
5. 记录涉及的应用/App、系统类型、是否需要登录/验证码
6. 为每个关键步骤选择最具代表性的 1 张截图
7. 综合画面和音频文本，撰写每个步骤的：名称、详细操作说明、补充说明

### 5. 构造生成配置

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

### 6. 生成 Word 文档

使用 skill 中的脚本生成最终文档：

```bash
python "C:/Users/13251/.workbuddy/skills/video-to-rpa-doc/scripts/gen_doc.py" <output_dir>/config.json
```

脚本会：
- 复制模板文件到输出路径
- 替换封面 3 个浮动文本框：标题、副标题、版本+日期（影刀RPA logo 和装饰线保持不动）
- 填写「流程基本信息」表
- 填写「应用系统」表并删除多余空行（**影刀RPA 不在系统列表中**）
- 填写「详细步骤解析」表，每步2行：**蓝色行第一列显示步骤名称**，白色行第一列显示描述、第二列插入截图（**无空行**）、第三列补充说明。表头自动修正为「步骤名称及详细说明 | 截图 | 其他补充说明及资料」，并删除多余空行
- **自动删除文档末尾因模板结构产生的空白页**（包括空白段落、lastRenderedPageBreak、页面分隔符等）

### 7. 用 Draw.io 生成流程图

> ⚠️ **强制规则（MUST）**：
> 1. Word 文档生成后**必须**调用 **`Skill drawio`** 生成流程图，不允许省略此步骤。
> 2. **严禁**再调用旧的 `scripts/gen_flowchart.py`（Mermaid 版本，已废弃）。
> 3. 若因任何原因未能生成 `.drawio` 文件，必须在最终回复中显式向用户说明原因，不得静默跳过。
> 4. 存在 `_flowchart.html` / `_flowchart.mmd` 等旧产物时必须先删除，避免混淆。

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

### 8. 输出与确认

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

**Q: 音频转录失败了？**
A: 检查网络连接，确认环境变量 `YINGDAO_AUTH_TOKEN` 和 `YINGDAO_WORKFLOW_ID` 已正确设置且仍然有效。如工作流有变更需同步更新环境变量。

**Q: ffmpeg 未找到？**
A: 安装 `imageio-ffmpeg` 即可获得内置便携版 ffmpeg：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple imageio-ffmpeg
```
确认安装成功后运行：
```bash
python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

**Q: 转录文本太长怎么办？**
A: 转录后的文本文件会自动保存，AI 可直接阅读文本文件进行分析。对于超长视频（>30分钟），可以分片段转录或让 AI 分段阅读。

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

**Q: 应用系统表的Yes/No/无等短答案没有居中？**
A: WPS 对 `w:jc`（段落居中）和 TabStop 制表位在表格数据单元格中均不生效。gen_doc.py 使用 `w:ind` 左缩进方案，根据单元格宽度和文字数动态计算偏移量实现视觉居中。如果需要调整居中精度，修改 `set_cell_text` 函数中的 `160`（每字符 twips 估值）。

**Q: WPS 与 Word 的表格单元格对齐有何不同？**
A: Word 能正确渲染 `w:jc w:val="center"` 在表格单元格中，但 WPS 在数据行中会忽略此属性（表头行不受影响）。gen_doc.py 已用 `w:ind` 替代 `w:jc` 实现跨编辑器兼容。

## 脚本文件

- `scripts/extract_audio.py`: 从视频中提取音频（16kHz mono WAV）
- `scripts/asr_transcribe.py`: 通过影刀 AI Work OS 语音识别工作流转录音频为文字
- `scripts/extract_frames.py`: 视频关键帧提取（OpenCV 场景检测）
- `scripts/gen_doc.py`: 根据 JSON 配置生成 Word 文档
- `references/影刀RPA需求文档模板.docx`: 标准 Word 模板
- `references/yingdao_logo.jpeg`: 封面页影刀 RPA logo
- `references/template_structure.md`: 模板结构说明
