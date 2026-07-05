---
name: video-mashup-to-jianying
description: |
  输入本地视频文件夹路径和产品卖点描述，随机抽选N个视频，
  通过豆包视觉理解模型分析视频画面内容，再汇总所有画面分析，
  一次性生成有起承转合的连贯卖货脚本（而非独立片段文案），
  然后生成对应的TTS音频，最终组合为剪映草稿。
  适用于电商带货混剪、产品种草视频批量制作。
  无需AI生成视频素材，直接复用本地视频，成本极低。
trigger:
  - 混剪
  - 混剪视频
  - 视频混剪
  - 批量混剪
  - 带货混剪
  - 产品混剪
  - 视频组合
  - 卖货视频
  - mashup
---

# 视频混剪 + 剪映草稿 一键生成

## 适用场景

本地有一批产品介绍视频（如10-100个），想要随机抽选几个，配上AI生成的卖货文案和语音，快速组合成一个带货短视频。

**与 doubao-media-to-jianying 的区别**：
- 原 skill：主题 → AI生成图片/视频素材 → 组合（需要生成素材，成本高）
- 本 skill：本地视频 → AI看画面生成文案 → 配TTS → 组合（复用本地视频，成本极低）

---

## 前置条件

### 1. Skill 目录（自包含）
所有脚本和配置文件均位于本 skill 目录下：`{SKILL_DIR}`

核心文件：
- `volcengine_api.py` — 火山引擎 API 封装（视频帧抽取/视觉理解/连贯文案生成/TTS + 费用统计 + 用时统计）
- `jianying_draft_composer.py` — 剪映草稿组合脚本
- `.env` — API 密钥和计费单价配置（已预填用户密钥）
- `.env.example` — 配置模板
- `火山引擎密钥获取指南.md` — 如果还不知道怎么拿三个密钥，先看这个

> Skill 运行时从 `{SKILL_DIR}` 加载模块和 `.env`，无需依赖外部路径。

### 2. Python 环境
系统 Python 3.11：`C:/Users/13251/AppData/Local/Programs/Python/Python311/python.exe`

已安装依赖：`volcengine-python-sdk[ark]`, `python-dotenv`, `requests`, `Pillow`, `pyJianYingDraft`, `opencv-python-headless`

### 3. 剪映草稿目录 ⚠️ 重要

**必须直接在剪映草稿目录下创建草稿**，这样剪映打开后直接就能看到项目，无需手动导入：

```
C:\Users\13251\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft
```

- 此路径从 `.env` 的 `JIANYING_DRAFT_PATH` 读取
- 若用户剪映安装路径不同，修改 `.env` 即可
- **不要**将草稿创建在 skill 的 output 目录下，那只是中间产物，不是最终交付
- 草稿创建后，打开剪映 → 「我的项目」即可看到

### 4. 本地视频文件
用户需要提供一个包含视频文件的文件夹路径。支持格式：`.mp4`, `.mov`, `.avi`, `.mkv`, `.flv`, `.wmv`, `.webm`, `.m4v`

---

## 执行流程

### Step 0: 收集必要参数

从用户输入中提取以下参数。**缺少的必要参数必须用 AskUserQuestion 询问用户**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| folder_path | str | ✅ | — | 本地视频文件夹路径 |
| product_desc | str | ✅ | — | 产品卖点描述，如"清风卫生纸，柔然又好用" |
| video_count | int | ❌ | 6 | 随机抽选视频数量 |
| draft_name | str | ❌ | 产品名+时间戳 | 剪映草稿名称 |
| frame_count | int | ❌ | 4 | 每个视频抽取的帧数（用于AI理解，建议3-6） |
| voice | str | ❌ | .env默认 | TTS音色（2.0音色需配合TTS_RESOURCE_ID=seed-tts-2.0） |
| add_video_movement | bool | ❌ | True | 视频是否添加运镜效果 |
| split_subtitles | bool | ❌ | True | 是否拆分字幕为短句 |
| mute_original_video | bool | ❌ | True | 是否对原视频静音（混剪场景通常True） |
| crop_video | bool | ❌ | True | 视频长于音频时是否裁剪 |
| background_music | str | ❌ | None | 背景音乐路径 |

#### ⚠️ 参数说明

**folder_path**：必须是包含视频文件的文件夹路径。脚本会递归扫描子文件夹。如果文件夹中视频数量少于 video_count，会全部使用并告知用户。

**product_desc**：产品名称+卖点描述。越详细，AI生成的文案越精准。
- 好的例子："清风卫生纸，三层加厚，柔然又好用，吸水性强不易破"
- 差的例子："卫生纸"（太简略，AI不知道该突出什么卖点）

**video_count**：默认6个。建议4-8个，太少内容单薄，太多视频时长过长。
- 每个视频约10-20秒文案 → 6个视频约1-2分钟成片

**frame_count**：每个视频抽取多少帧供AI分析。默认4帧。
- 3帧：够用，token消耗少
- 4帧：推荐，平衡效果和成本
- 6帧：更精细，但token消耗增加

**mute_original_video**：混剪场景默认True（静音原视频，用TTS替代）。如果原视频有重要声音需要保留，设为False。

**crop_video**：默认True。当视频比音频长时，裁剪视频到音频长度。设为False则会调整视频速度来匹配音频。

---

### 📐 音视频对齐机制（v4+）

Phase 2 生成文案时，**每段文案的字数由该视频的实际时长动态决定**，确保音频和视频等长播放，避免视频被加速 5-10 倍或明显慢放。

**计算公式**（在 `calc_target_chars()` 中）：
```
目标字数 ≈ (视频时长 - 0.5秒余量) × 4字/秒 × 语速倍率
```
- 4字/秒 是普通口播基准语速
- 语速倍率由 `TTS_SPEECH_RATE` 决定，如 25 → 1.25 倍 → 5字/秒
- 例：视频 6秒 + 1.25倍速 → 目标 (6-0.5)×5 ≈ 27 字

**Prompt 约束**：AI 会看到每段的目标字数区间（如 "目标 24-30 字"），必须严格生成，允许 ±5 字误差。

**日志验证**：控制台会打印每段的 `时长/目标字数/实际字数` 三元组，带 ✅（偏差≤5）或 ⚠️（偏差>5）标识，便于快速核对。

---

### Step 1: 调用混剪素材生成

在 skill 目录 `{SKILL_DIR}` 下执行 Python 代码：

```python
import sys
sys.path.insert(0, r"{SKILL_DIR}")

# 重新加载模块（避免缓存旧版本）
if "volcengine_api" in sys.modules:
    del sys.modules["volcengine_api"]

from volcengine_api import generate_mashup_pack, tracker

result = generate_mashup_pack(
    folder_path=r"{folder_path}",
    product_desc="{product_desc}",
    video_count={video_count},
    frame_count={frame_count},
    voice={voice},  # None 使用默认
)
```

**注意**：
- `generate_mashup_pack` 会自动完成两阶段处理：
  - **Phase 1**：并发分析所有视频画面（只描述画面，不写文案）
  - **Phase 2**：汇总所有画面分析 + 产品卖点，一次性生成有起承转合的连贯卖货脚本（每段对应一个视频，但整体像一个主播从头讲到尾）
  - 然后并发生成 TTS 音频
- 返回字典结构：
  ```python
  {
      "product_desc": str,
      "video_paths": [str],          # 选中的视频路径列表
      "storyboard": [
          {
              "index": int,
              "video_path": str,
              "video_analysis": str,  # AI对视频画面的分析
              "sales_copy": str,       # 生成的卖货文案
              "frames_extracted": int, # 实际抽取的帧数
          }, ...
      ],
      "audio_paths": [str|None],      # TTS音频文件路径列表
      "media_paths": [str],           # 视频文件路径列表（= video_paths）
      "subtitle_texts": [str],        # 卖货文案列表（= sales_copy）
      "elapsed_seconds": float,       # 生成总用时（秒）
  }
  ```

### Step 2: 调用剪映草稿组合脚本

素材生成完成后，调用组合脚本创建剪映草稿：

```python
import sys
sys.path.insert(0, r"{SKILL_DIR}")

from importlib import import_module
combo = import_module("jianying_draft_composer")

# 构建参数
subtitles = result["subtitle_texts"]
audio_paths = [p for p in result["audio_paths"] if p is not None]
media_paths = result["media_paths"][:len(audio_paths)]  # 对齐长度

# ⚠️ 剪映草稿目录：必须用 JIANYING_DRAFT_PATH，不要在 output 目录下创建
# 这样剪映打开后直接就能看到项目，无需手动导入
import os
from dotenv import load_dotenv
load_dotenv(rf"{SKILL_DIR}/.env", override=True)
draft_folder_path = os.getenv("JIANYING_DRAFT_PATH", r"C:\Users\13251\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft")
draft_name = "{draft_name}"  # 默认用产品名+时间戳

combo.create_jianying_draft_with_media(
    draft_name=draft_name,
    subtitle_texts=subtitles[:len(audio_paths)],
    audio_paths=audio_paths,
    media_paths=media_paths,
    draft_folder_path=draft_folder_path,
    add_video_movement={add_video_movement},
    split_subtitles={split_subtitles},
    mute_original_video={mute_original_video},
    crop_video={crop_video},
    background_music={background_music},  # None 如果没有
)
```

**注意**：
- 如果某些片段的 TTS 生成失败（路径为 None），需要过滤掉对应的片段
- `subtitle_texts`、`audio_paths`、`media_paths` 三个列表长度必须一致
- 如果剪映草稿已存在，需要换一个草稿名称

### Step 3: 输出结果汇总

向用户输出以下信息：

1. ✅ 剪映草稿创建成功提示
2. 📝 草稿名称
3. 🎬 选中的视频列表 + 对应的文案
4. 💰 **生成此剪映草稿花费：¥{total_cost:.4f}**
5. ⏱️ **生成用时：{elapsed_seconds} → 格式化为 X分Y秒**

```python
# 获取费用和用时
total_cost = sum(item["cost"] for item in tracker.items)
elapsed = result["elapsed_seconds"]

# 格式化用时
mins, secs = divmod(int(elapsed), 60)
if mins >= 1:
    time_str = f"{mins}分{secs}秒"
else:
    time_str = f"{elapsed:.1f}秒"
```

---

## 费用预估

混剪 skill 不需要AI生成视频/图片素材，成本极低：

| 环节 | 单价 | 6个视频预估 |
|------|------|------------|
| 视觉理解（4帧/视频） | ¥0.003/千输入tokens + ¥0.009/千输出tokens | ~¥0.05 |
| 连贯文案生成（文本模型） | ¥0.0008/千输入tokens + ¥0.002/千输出tokens | ~¥0.001 |
| TTS语音合成 | ¥5/万字符 | ~¥0.15 |
| **合计** | — | **~¥0.2** |

---

## TTS 音色与语速配置

通过 `.env` 文件配置音色和语速，无需改代码：

### 音色配置

| .env 参数 | 说明 |
|-----------|------|
| `TTS_VOICE` | 音色ID，如 `zh_female_kailangjiejie_uranus_bigtts` |
| `TTS_RESOURCE_ID` | 资源ID：1.0音色用 `volc.service_type.10029`，2.0音色用 `seed-tts-2.0` |
| `TTS_SPEECH_RATE` | 语速：[-50,100]，0=正常，100=2.0倍速，-50=0.5倍速。公式：(目标倍速-1.0)×100 |

### 卖货推荐音色

| 音色 | speaker ID | 风格 | 资源ID |
|------|-----------|------|--------|
| 开朗姐姐 2.0 | `zh_female_kailangjiejie_uranus_bigtts` | 开朗亲切，适合互动卖货 | `seed-tts-2.0` |
| 爽快思思 2.0 | `zh_female_shuangkuaisisi_uranus_bigtts` | 爽快风格，适合快节奏卖货 | `seed-tts-2.0` |
| 林潇 2.0 | `zh_female_linxiao_uranus_bigtts` | 抖音同款 | `seed-tts-2.0` |
| 甜美桃子 2.0 | `zh_female_tianmeitaozi_uranus_bigtts` | 甜美风格，适合快消品 | `seed-tts-2.0` |

### 常用语速参考

| 倍速 | TTS_SPEECH_RATE 值 |
|------|-------------------|
| 1.0x（正常） | 0 |
| 1.25x | 25 |
| 1.5x | 50 |
| 1.75x | 75 |
| 2.0x（最快） | 100 |

> 对比原 skill（图片模式6分镜约¥1.5，视频模式约¥10-25），混剪 skill 成本仅为 **1/10 到 1/100**！

---

## 常见问题

### Q: 文件夹中视频不够怎么办？
脚本会自动使用全部视频并告知用户。比如文件夹只有4个视频但 video_count=6，会使用全部4个。

### Q: 视觉理解模型分析失败？
脚本有兜底机制：如果视觉理解失败，会生成通用文案（如"今天给大家推荐XX，真的很好用"），不会中断流程。

### Q: 视频格式不支持？
支持常见格式：mp4, mov, avi, mkv, flv, wmv, webm, m4v。如果遇到不支持的格式，需要先转换。

### Q: 剪映草稿已存在？
`create_jianying_draft_with_media` 不允许覆盖，需要换一个草稿名称。默认会加上时间戳避免冲突。

### Q: 视频横竖屏混用？
脚本会使用第一个视频的尺寸作为草稿尺寸。建议混剪时尽量使用相同方向的视频。如果混用，可以在剪映中手动调整。

### Q: 如何调整文案风格？
修改 `volcengine_api.py` 中 `generate_coherent_script` 函数的 prompt 即可。可以调整文案长度、语气、风格、段落过渡方式等。

### Q: 文案是连贯的还是独立的？
采用**两阶段架构**：Phase 1 只分析每个视频画面，Phase 2 汇总所有画面分析后一次性生成连贯脚本。整体像一个主播从头讲到尾，有起承转合——第一段吸引注意力引出产品，中间段落展示不同卖点，最后一段有行动号召。

---

## 示例对话

**用户**：我有个文件夹 D:\videos\products 里面有100个产品视频，帮我做一个清风卫生纸的混剪，抽6个视频

**助手**：
1. 确认参数：folder_path=D:\videos\products, product_desc="清风卫生纸", video_count=6
2. 调用 `generate_mashup_pack(folder_path=r"D:\videos\products", product_desc="清风卫生纸", video_count=6)`
3. Phase 1: 并发分析6个视频画面 → Phase 2: 生成连贯卖货脚本 → TTS音频
4. 调用 `create_jianying_draft_with_media(...)`
5. 输出：剪映草稿"清风卫生纸_20260703"创建成功！花费：¥0.18，用时：45.2秒

**用户**：产品是清风卫生纸，三层加厚柔然又好用，抽8个视频，文件夹在 E:\product_videos

**助手**：
1. 调用 `generate_mashup_pack(folder_path=r"E:\product_videos", product_desc="清风卫生纸，三层加厚柔然又好用", video_count=8)`
2. AI会看每个视频画面，结合"三层加厚""柔然"等卖点生成针对性文案
3. 输出结果
