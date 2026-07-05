---
name: doubao-media-to-jianying
description: |
  输入主题，调用火山引擎（豆包）API 自动生成故事化分镜文案、TTS 音频、风格统一的图片/视频素材，
  然后一键组合为剪映草稿。最后输出费用明细和用时。
  文案以叙事驱动，自然有代入感；所有素材视觉风格统一协调。支持图片模式和视频模式。
trigger:
  - 生成短视频
  - 一键生成剪映草稿
  - 豆包生成素材
  - 生成素材包
  - 主题生成视频
  - 主题生成图片
  - doubao media
---

# 豆包素材生成 + 剪映草稿 一键组合

## 前置条件

### 1. Skill 目录（自包含）
所有脚本和配置文件均位于本 skill 目录下：`{SKILL_DIR}`

核心文件：
- `volcengine_api.py` — 火山引擎 API 封装（文案/TTS/文生图/文生视频 + 费用统计 + 用时统计）
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

---

## 执行流程

### Step 0: 收集必要参数

从用户输入中提取以下参数。**缺少的必要参数必须用 AskUserQuestion 询问用户**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| topic | str | ✅ | — | 视频主题，如"量子力学""再别康桥" |
| mode | str | ✅ | "image" | 素材模式，见下方说明 |
| draft_name | str | ❌ | 用主题命名 | 剪映草稿名称 |
| add_image_movement | bool | ❌ | True | 图片是否添加运镜效果 |
| add_video_movement | bool | ❌ | True | 视频是否添加运镜效果 |
| split_subtitles | bool | ❌ | True | 是否拆分字幕为短句 |
| mute_original_video | bool | ❌ | False | 是否对视频静音（视频模式下常用 True） |
| crop_video | bool | ❌ | False | 视频长于音频时是否裁剪 |
| background_image | str | ❌ | None | 背景图片路径 |
| background_music | str | ❌ | None | 背景音乐路径 |

#### ⚠️ 关于 mode 参数（重要！）

**用户说"生成视频"≠ mode="video"！** 必须区分清楚：

| mode | 素材类型 | 速度 | 单素材费用 | 最终产出 |
|------|----------|------|------------|----------|
| `"image"` | AI生图 + TTS音频 | ⚡ 快（约30秒/分镜） | 💰 ¥0.25/张 | 剪映草稿→可导出为视频 |
| `"video"` | AI生视频 + TTS音频 | 🐢 慢（约1-3分钟/分镜） | 💸 ¥1-4/条（按tokens计） | 剪映草稿→可导出为视频 |

**大多数场景推荐 `mode="image"`**：图片+音频→剪映草稿→导出视频，效果已经很好。

**判断规则**：
- 用户说"生成视频"或"做个短视频" → 通常指最终想要视频，**默认 mode="image"**（图片配音频）
- 用户明确说"AI视频"或"生成动态视频素材" → mode="video"
- 如果不确定，**必须用 AskUserQuestion 询问**，选项说明要清晰：

```
AskUserQuestion:
  header: "素材模式"
  question: "请选择素材模式，两种最终都可以在剪映导出为视频："
  options:
    - label: "图片模式（推荐）"
      description: "AI生成静态图片+运镜效果，快速便宜，约 ¥0.25/张（4个分镜约¥1）"
    - label: "视频模式"
      description: "AI生成动态视频片段，每条约1-3分钟，约 ¥1-4/条（4个分镜约¥5-15）"
```

#### 🎭 文案风格与视觉统一

**文案讲究故事性**：
- 字幕不再是口号式广告语，而是叙事驱动的对话体
- 像朋友聊天一样自然，有情感张力，杜绝"颠覆""燃爆""超乎想象"等AI套话
- 分镜间有叙事推进：铺垫→展开→高潮→余味

**视觉风格统一协调**：
- AI会自动为所有分镜选定统一的画风、色调、光影体系
- 所有 image_prompt 共享相同的风格前缀，确保素材视觉一致
- 在 topic 中可附加风格要求（如"动漫风格""赛博科技感"），AI会融入统一体系

### Step 1: 调用豆包 API 生成素材

在 skill 目录 `{SKILL_DIR}` 下执行 Python 代码：

```python
import sys
sys.path.insert(0, r"{SKILL_DIR}")

# 重新加载模块（避免缓存旧版本）
if "volcengine_api" in sys.modules:
    del sys.modules["volcengine_api"]

from volcengine_api import generate_media_pack, tracker

result = generate_media_pack(
    topic="{topic}",
    mode="{mode}",             # "image"（推荐）或 "video"
)
```

**注意**：
- 由于 `volcengine_api.py` 在 import 时会加载 `.env` 并初始化 Ark 客户端，必须先 `sys.path.insert` 确保模块能找到
- `generate_media_pack` 返回字典结构：
  ```python
  {
      "topic": str,
      "storyboard": [{"index", "subtitle", "image_prompt", "video_prompt"}, ...],
      "audio_paths": [str|None, ...],   # 音频文件路径列表
      "media_paths": [str|None, ...],    # 图片或视频文件路径列表
      "elapsed_seconds": float,          # 生成总用时（秒）
  }
  ```
- 素材默认保存在 `{SKILL_DIR}\output\{主题}\` 下

### Step 2: 调用剪映草稿组合脚本

素材生成完成后，调用组合脚本创建剪映草稿：

```python
import sys
sys.path.insert(0, r"{SKILL_DIR}")

from importlib import import_module
# 导入剪映草稿组合模块
combo = import_module("jianying_draft_composer")

# 构建参数
subtitles = [s["subtitle"] for s in result["storyboard"]]
audio_paths = [p for p in result["audio_paths"] if p is not None]
media_paths = [p for p in result["media_paths"] if p is not None]

# ⚠️ 剪映草稿目录：必须用 JIANYING_DRAFT_PATH，不要在 output 目录下创建
# 这样剪映打开后直接就能看到项目，无需手动导入
import os
from dotenv import load_dotenv
load_dotenv(rf"{SKILL_DIR}/.env", override=True)
draft_folder_path = os.getenv("JIANYING_DRAFT_PATH", r"C:\Users\13251\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft")
draft_name = "{draft_name}"  # 默认用主题命名

combo.create_jianying_draft_with_media(
    draft_name=draft_name,
    subtitle_texts=subtitles,
    audio_paths=audio_paths,
    media_paths=media_paths,
    draft_folder_path=draft_folder_path,
    add_image_movement={add_image_movement},
    add_video_movement={add_video_movement},
    split_subtitles={split_subtitles},
    mute_original_video={mute_original_video},
    crop_video={crop_video},
    background_image={background_image},     # None 如果没有
    background_music={background_music},     # None 如果没有
)
```

**注意**：
- 如果剪映草稿目录不存在，检查 `.env` 中 `JIANYING_DRAFT_PATH` 是否正确配置为 `C:\Users\13251\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft`
- `subtitle_texts`、`audio_paths`、`media_paths` 三个列表长度必须一致
- 如果某些分镜的音频/媒体生成失败（路径为 None），需要过滤掉对应的分镜

### Step 3: 输出结果汇总

向用户输出以下信息：

1. ✅ 剪映草稿创建成功提示
2. 📝 草稿名称
3. 🎬 分镜内容列表（每个分镜的字幕）
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

## 常见问题

### Q: 视频模式很慢？
文生视频每个分镜需要 1-3 分钟轮询，建议分镜数不超过 5 个。大多数场景用图片模式即可。

### Q: 图片生成尺寸？
图片默认 1920×1080（先生成 2560×1440 再缩放），视频默认 1080p 16:9 (1920×1080)。

### Q: 某些分镜素材生成失败？
`generate_media_pack` 返回中失败的项为 `None`，组合剪映草稿时需过滤掉。如果有分镜失败，告知用户哪些分镜失败了，但继续用成功的分镜创建草稿。

### Q: 剪映草稿已存在？
`create_jianying_draft_with_media` 不允许覆盖，需要换一个草稿名称。

### Q: 费用预估？
- 文案生成：几乎忽略（几厘钱）
- TTS：几厘钱（按字符数）
- 文生图：¥0.25/张（固定）
- 文生视频：¥1-4/条（按 tokens 计算，有声 ¥16/百万tokens）
- **图片模式下一个 5 分镜素材包约 ¥1.3**
- **视频模式下一个 5 分镜素材包约 ¥8-20**

---

## 示例对话

**用户**：帮我生成一个关于量子力学的短视频并创建剪映草稿

**助手**：（用户说"短视频"，没指定素材模式，需要询问）
→ AskUserQuestion: "请问素材用图片还是AI视频？图片模式更快更便宜，最终都可以导出为视频。"
   - 图片模式（推荐）：AI生成静态图片+运镜效果，快速便宜，约¥0.25/张
   - 视频模式：AI生成动态视频片段，每条1-3分钟，约¥1-4/条

**用户**：图片模式

**助手**：
1. 调用 `generate_media_pack(topic="量子力学", mode="image")`
2. 等待素材生成完成
3. 调用 `create_jianying_draft_with_media(...)`
4. 输出：剪映草稿"量子力学"创建成功！花费：¥1.29，用时：28.5秒

**用户**：帮我生成再别康桥的剪映草稿

**助手**：（诗词主题，AI会自动全文分镜）
1. 调用 `generate_media_pack(topic="再别康桥", mode="image")`
2. AI自动按诗句分镜，覆盖全文
3. 输出结果
