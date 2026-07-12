---
title: "Video Batch to RPA Requirements Collection Excel"
summary: "给定一个文件夹（含多个客户工作录屏视频，文件名格式为 部门_需求提交人_工作流程名称.mp4），批量提取关键帧、用多模态大模型视觉分析每个视频的业务步骤，最终按指定模板输出一份需求收集 Excel 表，缺失字段自动高亮黄色并标注 ⚠待补充。"
agent_created: true
---

# 批量录屏 → RPA 需求收集表 (Excel)

这个 skill 用于**批量处理一个文件夹里的客户工作录屏**，自动整理出**需求收集表 Excel**。

与 `video-to-rpa-doc` 单视频生成 Word 文档不同，本 skill 的目标是：
- **一次处理一整个文件夹的视频**
- 自动从文件名解析「部门 / 需求提交人 / 工作流程名称」
- 对每个视频做关键帧提取 + 多模态视觉分析，还原工作步骤
- 输出统一的 Excel 收集表（按模板）
- **缺失字段自动高亮黄色 + ⚠待补充**，交给业务人员补齐

## 触发场景

- 用户说：「我这里有一堆录屏，帮我整理成需求收集表」
- 用户给出一个文件夹路径，里面很多 mp4 文件，想要批量梳理
- 用户说：「按这个 Excel 模板把这些视频都整理进去」
- 用户强调：「文件名里可能缺部门/提交人，你帮我标出来让业务补」

## 前置要求

### Python 依赖

```bash
pip install opencv-python openpyxl pillow imageio-ffmpeg requests
```

（venv 路径：`C:/Users/13251/.workbuddy/binaries/python/envs/default/Scripts/python.exe`，已预装 cv2、openpyxl、requests）

### ASR 凭证（可选）

若设置以下环境变量，将启用**影刀 AI 语音转文字**辅助步骤还原（识别率更高）；未设置时自动跳过 ASR，纯视觉分析。

| 环境变量 | 说明 |
|---------|------|
| `YINGDAO_AUTH_TOKEN` | 影刀开放平台 Bearer Token |
| `YINGDAO_WORKFLOW_ID` | 影刀语音转文字工作流 ID |

未配置不会报错，流程自动降级为纯视觉分析。

## 处理流程

### 1. 接收输入

| 输入项 | 说明 | 默认值 |
|--------|------|--------|
| `video_folder` | 存放客户录屏的文件夹 | 用户指定（如 `D:/Desktop/录屏/`）|
| `template_path` | Excel 模板路径 | `~/.workbuddy/skills/video-to-rpa-collect/references/需求收集模板.xlsx` |
| `output_dir` | 工作目录（关键帧、json、最终xlsx输出位置）| 当前 workspace 下的 `rpa_collect_YYYYMMDD/` |

**文件命名约定**（重要）：
- 规范格式：`部门_需求提交人_工作流程名称.mp4`
  - 例：`运营_延慧美_设置各类促销.mp4`、`财务_张三_发票核验.mp4`
- 允许变体（会自动降级处理）：
  - `部门_工作流程名称.mp4`（两段）→ 缺「需求提交人」，标黄色
  - `工作流程名称.mp4`（一段）→ 缺「部门」+「需求提交人」，标黄色
  - 其他命名（三段以上）→ 前两段当作部门/提交人，其余拼接为流程名
- 支持的视频后缀：`.mp4 / .mov / .avi / .mkv / .wmv / .flv / .webm / .m4v`

### 2. 扫描文件夹 → 生成初始 JSON

```bash
PY=C:/Users/13251/.workbuddy/binaries/python/envs/default/Scripts/python.exe
$PY "C:/Users/13251/.workbuddy/skills/video-to-rpa-collect/scripts/gen_excel.py" scan \
    "<video_folder>" \
    --output "<output_dir>/需求收集表.xlsx" \
    --json-out "<output_dir>/config.json"
```

这一步会：
1. 递归扫描文件夹下所有视频
2. 按命名规则解析「部门 / 提交人 / 工作流程名称」
3. 未解析出来的字段列入 `missing_fields`
4. 生成 `config.json`，每条 item 结构如下：

```json
{
  "template_path": ".../references/需求收集模板.xlsx",
  "output_path": "<output_dir>/需求收集表.xlsx",
  "items": [
    {
      "video_file": "D:/Desktop/录屏/运营_延慧美_设置各类促销.mp4",
      "video_filename": "运营_延慧美_设置各类促销.mp4",
      "department": "运营",
      "submitter": "延慧美",
      "workflow_name": "设置各类促销",
      "steps": null,
      "pain_points": null,
      "systems": null,
      "enterprise": null,
      "missing_fields": ["具体工作步骤说明", "业务痛点", "涉及到的软件系统和网页", "企业名称"]
    }
  ]
}
```

### 3. 批量提取音频 + ASR（可选，推荐）

> 若设置了影刀 ASR 环境变量，会先尝试音频提取与语音转文字；若视频无音频轨道会自动标记 `has_audio: false`，后续纯视觉分析；若环境变量未配置则跳过此步。

```bash
$PY "C:/Users/13251/.workbuddy/skills/video-to-rpa-collect/scripts/batch_asr.py" \
    "<output_dir>/config.json"
```

这一步会：
- 在每个视频的 `work_dir` 下生成 `audio.wav`（16kHz 单声道 WAV，供 ASR 使用）
- 若配置了影刀凭证，调用影刀语音转文字工作流生成 `transcript.txt`，并把文字回写到 item 的 `transcript` 字段
- 若视频无音频轨道（ffmpeg 报 `Output file does not contain any stream`），标记 `has_audio: false`，不会报错，继续走视觉分析
- 可用 `--skip-asr` 参数只提取音频不做转写（调试用）

### 4. 批量提取关键帧

```bash
$PY "C:/Users/13251/.workbuddy/skills/video-to-rpa-collect/scripts/batch_extract_frames.py" \
    "<output_dir>/config.json" \
    "<output_dir>" \
    --threshold 30 \
    --min-interval 1.5 \
    --frame-skip 5 \
    --max-frames 15
```

这一步会：
- 在 `output_dir` 下为每个视频创建子目录（按文件名命名）
- 每个子目录下生成 `video_frames/`，存放关键帧 PNG
- 对每个视频，默认参数下提取关键帧；若帧数超过 `--max-frames` 会自动提高阈值重试
- 更新 `config.json`，向每个 item 写入 `frames_dir`、`frames`（PNG 文件列表）、`frames_count`

**参数调优建议**：
- 视频短且操作密集：`--min-interval 0.8 --threshold 25`
- 视频长且操作稀疏：`--min-interval 2.5 --threshold 40`
- 视频非常多（>20 个）：加大 `--frame-skip 10` 加快速度

### 5. 多模态视觉分析 + ASR 文本融合（核心步骤）

> ⚠️ **强制规则（MUST）**：
> 1. **必须逐个视频**分析，不能跳视频。
> 2. **必须按时间顺序查看 frames_dir 下所有 PNG 关键帧**（用 Read 工具看图片），结合画面判断：
>    - 视频展示的是什么业务流程（确认/修正 workflow_name）
>    - 操作涉及了哪些软件系统/网页（填入 systems，多系统用顿号分隔）
>    - 业务里有哪些繁琐/重复/容易出错的地方（作为 pain_points）
> 3. **若有 transcript（ASR 转写文本），必须结合讲解内容还原步骤**——客户录屏通常边操作边讲解，ASR 文本对步骤命名、业务术语、判断分支非常有价值。把语音讲解和画面操作交叉印证，不要只看画面忽略语音。
> 4. **步骤描述必须是 1,2,3... 编号列表**，每个步骤一句话，用换行符 `\n` 分隔。格式参考：
>    ```
>    1. 打开京麦后台，进入营销-促销工具首页
>    2. 创建单促：填写活动名称、选择季度时间、导入商品表格
>    3. 创建赠品促销：筛选进行中的赠品活动，复制后重命名改时间
>    4. 创建礼金促销：同赠品流程，选中进行中的礼金活动复制
>    ```
> 4. 如果画面里能看到公司/店铺名称，自动填到 `enterprise` 字段；看不到则留空（标黄待补）
> 5. **严禁凭记忆编造步骤**。画面+语音信息都不足时，steps 字段留 null（标黄待补），不要虚构。
> 6. 分析完一个视频后，**立即把结果写回 config.json 的对应 item**（使用 Edit 工具或重新写回整个文件），不要攒到最后一次性写，避免中断丢失进度。
> 7. 若从画面判断出部门/提交人/流程名和文件名解析不一致，以画面（或语音讲解）为准，并在回复中说明差异。

**分析顺序建议**：
- 若有 transcript，**先读语音转写文本**建立整体流程框架，客户的口头讲解通常会直接说出步骤目的、系统名称和痛点
- 再整体扫一遍所有帧（看首尾帧建立业务域直觉）
- 按时间顺序逐帧核对语音讲解与画面操作是否一致，修正 ASR 识别错误的术语
- 合并相邻的微小步骤（比如连续 3 帧都是"点击按钮→等待加载→新页面出现"可以合并为一步）
- 步骤数建议控制在 **5~15 步**，太粗太细都不合适

### 6. 生成 Excel

所有视频分析完成后，执行：

```bash
$PY "C:/Users/13251/.workbuddy/skills/video-to-rpa-collect/scripts/gen_excel.py" \
    "<output_dir>/config.json"
```

这一步会：
- 复制模板到 `output_path`
- 删除模板中的示例行（第 2 行）
- 每个视频占一行，按 `部门 | 需求提交人 | 工作流程名称 | 具体工作步骤说明 | 业务痛点 | 涉及到的软件系统和网页 | 企业名称` 填充
- **缺失字段**自动填入 `⚠待补充`，单元格**黄色高亮**
- 表头蓝色加粗居中，数据行自动换行、根据步骤行数自动调整行高
- 冻结首行，列宽预设（步骤列最宽 60 字符）

### 7. 输出与交付

生成完成后：
1. 使用 `present_files` 展示最终 Excel 文件
2. **明确告知 Excel 文件绝对路径**
3. 在回复中提供一份**缺失字段汇总清单**，格式示例：

```
📊 本次共处理 12 个视频，已生成需求收集表：<path>

⚠️ 需要补充的字段（黄色单元格）：
- 视频1「运营_设置各类促销.mp4」：缺需求提交人
- 视频3「_张三_发票核验.mp4」：缺部门；企业名称未能从画面识别
- 视频7「数据导出.mp4」：缺部门、缺需求提交人
- 视频11「xxx.mp4」：画面信息不足，具体工作步骤需要提交人补充

其余字段已从画面/文件名解析填充，请业务人员核对后补全黄色单元格。
```

4. 询问用户是否需要：
   - 对某些视频重新提取关键帧（调整阈值）
   - 对某些步骤做更细/更粗的拆分
   - 追加其他字段（比如「预计收益」「优先级」等）
   - 把 Excel 上传到飞书/腾讯文档

## 模板说明

标准模板：`C:/Users/13251/.workbuddy/skills/video-to-rpa-collect/references/需求收集模板.xlsx`

模板字段（表头固定 7 列，顺序不可变）：

| 列 | 表头 | 来源 | 缺失处理 |
|----|------|------|---------|
| A | 部门 | 文件名第一段 / 画面推断 | ⚠待补充 + 黄底 |
| B | 需求提交人 | 文件名第二段 / 画面推断 | ⚠待补充 + 黄底 |
| C | 工作流程名称 | 文件名其余段 / 画面推断 | ⚠待补充 + 黄底 |
| D | 具体工作步骤说明 | **AI 视觉分析**（1,2,3...编号）| ⚠待补充 + 黄底 |
| E | 业务痛点 | AI 视觉分析（推测繁琐/重复点）| ⚠待补充 + 黄底 |
| F | 涉及到的软件系统和网页 | AI 视觉分析（多系统顿号分隔）| ⚠待补充 + 黄底 |
| G | 企业名称 | 画面识别 | ⚠待补充 + 黄底 |

## 常见问题

**Q: 视频没有音频 / 影刀凭证没配怎么办？**
A: 没关系，batch_asr.py 会自动检测。无音频或无凭证的视频会被标记 `has_audio: false`，自动降级为纯视觉分析，流程不中断。有音频且配了凭证的视频会走「语音+画面」双模态，步骤还原更准确。

**Q: 文件名完全没有下划线，根本无法解析？**
A: department/submitter/workflow_name 都标为缺失，整行三个核心字段全黄。AI 从画面分析补 workflow_name，其余留给业务填。

**Q: 一个文件夹里有 30+ 个视频，关键帧太多看不过来？**
A: 调大 `--frame-skip 10 --min-interval 3.0 --max-frames 8`，每个视频压到 8 张以内。或者按子文件夹分批处理。

**Q: 能不能自动调用豆包多模态 API 识别，而不是让我一张张看？**
A: 当前设计是用 Read 工具逐张读图（主会话模型直接看图），零配置。如果未来需要接入豆包 API 批量识别，可以扩展 scripts/analyze_frames.py，但暂不强制。

**Q: 生成的 Excel 用 WPS/Office 打开样式对吗？**
A: 仅使用 openpyxl 标准样式（填充色、边框、对齐、字体、行高列宽、冻结窗格），WPS 和 Microsoft Excel 都能正确显示黄色高亮。

**Q: 模板被用户自己改了怎么办？**
A: 脚本会以 `template_path` 读取实际文件，删除第 2 行示例数据后从第 2 行开始写入。只要表头在第 1 行且列顺序一致，就能正确填充。

## 脚本文件

- `scripts/extract_frames.py`：单视频关键帧提取（OpenCV MSE 场景检测，复用自 video-to-rpa-doc）
- `scripts/batch_extract_frames.py`：批量提取（遍历 config.json 的 items，为每个视频创建子目录并提取关键帧，回写 frames_dir/frames 字段）
- `scripts/extract_audio.py`：单视频音频提取（imageio-ffmpeg 输出 16kHz 单声道 WAV，复用自 video-to-rpa-doc）
- `scripts/asr_transcribe.py`：单音频影刀语音转文字（上传音频 → 调用 ASR 工作流 → 输出 transcript.txt，复用自 video-to-rpa-doc）
- `scripts/batch_asr.py`：批量音频提取 + ASR（遍历 items，对每个视频提取音频并调用影刀转写；无音频自动标记跳过；未配凭证时只提音频不转写）
- `scripts/gen_excel.py`：核心脚本，两个入口：
  - `scan <folder>`：扫描文件夹生成初始 JSON
  - 默认模式：读取 config.json 生成 Excel
- `references/需求收集模板.xlsx`：需求收集 Excel 模板（7 列表头，含一行示例）

## 与 video-to-rpa-doc 的关系

| 维度 | video-to-rpa-doc | video-to-rpa-collect（本 skill）|
|------|------------------|--------------------------------|
| 处理量 | 单次 1 个视频 | 批量 N 个视频（整文件夹）|
| 输出 | Word 文档（封面+详细步骤+系统表）| Excel 收集表（一行一个需求）|
| 流程图 | 必须生成 .drawio | 不需要 |
| ASR | 影刀 AI 语音转文字（可选）| **影刀 AI 语音转文字（可选，有音频+凭证时自动启用，双模态融合还原步骤）** |
| 适用阶段 | 单个需求已确认，产出正式交付文档 | 需求收集期，批量梳理客户提交的录屏 |
| 缺失值 | 不允许缺失（向用户追问）| 标黄 ⚠待补充，由业务人员补齐 |
