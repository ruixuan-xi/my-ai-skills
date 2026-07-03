import os
import time
import base64
import requests
import json
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

# 加载环境变量（从同目录 .env 文件读取）
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ====================== 费用统计 ======================
class CostTracker:
    def __init__(self):
        self.items = []

    def add(self, task: str, cost: float, detail: str = ""):
        self.items.append({"task": task, "cost": cost, "detail": detail})

    def summary(self):
        if not self.items:
            return
        total = sum(i["cost"] for i in self.items)
        name_w  = max(len(i["task"]) for i in self.items) + 2
        cost_w  = 12
        print()
        print("=" * (name_w + cost_w + 18))
        print("  📊 本次调用费用明细")
        print("=" * (name_w + cost_w + 18))
        for i in self.items:
            print(f"  {i['task']:<{name_w}s}¥{i['cost']:<{cost_w}.6f}  {i['detail']}")
        print("-" * (name_w + cost_w + 18))
        print(f"  {'合计':<{name_w}s}¥{total:<{cost_w}.6f}")
        print("=" * (name_w + cost_w + 18))


tracker = CostTracker()


# ====================== 计费单价配置（元） ======================
def _float_env(name: str, default: float) -> float:
    try:
        val = os.getenv(name)
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        print(f"  ⚠️  .env 中 {name} 的值无法解析为数字，将使用默认值 {default}")
        return default


CHAT_INPUT_PRICE  = _float_env("CHAT_INPUT_PRICE",  0.002)
CHAT_OUTPUT_PRICE = _float_env("CHAT_OUTPUT_PRICE", 0.003)
TTS_PRICE_PER_10K = _float_env("TTS_PRICE_PER_10K", 5.0)
IMAGE_PRICE        = _float_env("IMAGE_PRICE", 0.25)
VIDEO_PRICE_AUDIO  = _float_env("VIDEO_PRICE_AUDIO",  16.0)
VIDEO_PRICE_SILENT = _float_env("VIDEO_PRICE_SILENT",  8.0)


# ====================== 全局配置 ======================
ARK_API_KEY = os.getenv("ARK_API_KEY")
VOLC_REGION = os.getenv("VOLC_REGION", "cn-beijing")

CHAT_MODEL_ID  = os.getenv("CHAT_MODEL_ID")
IMAGE_MODEL_ID = os.getenv("IMAGE_MODEL_ID")
VIDEO_MODEL_ID = os.getenv("VIDEO_MODEL_ID")

TTS_APP_ID       = os.getenv("TTS_APP_ID")
TTS_ACCESS_TOKEN = os.getenv("TTS_ACCESS_TOKEN")
TTS_CLUSTER      = os.getenv("TTS_CLUSTER", "volc.service_type.10029")
TTS_VOICE        = os.getenv("TTS_VOICE", "zh_female_shuangkuaisisi_moon_bigtts")

if not ARK_API_KEY:
    raise ValueError("请在 .env 文件中配置 ARK_API_KEY")
ark_client = Ark(api_key=ARK_API_KEY, region=VOLC_REGION)


# ====================== 图片/视频生成尺寸策略 ======================
# 图片：seedream 4.5 要求至少 3686400 像素
#   1920x1080 = 2073600（不满足）→ 先生成 2560x1440 再缩放
# 视频：SDK 支持 resolution + ratio 参数
IMAGE_GEN_SIZE      = "2560x1440"     # 图片 API 调用时的尺寸
IMAGE_TARGET_SIZE   = (1920, 1080)    # 图片生成后缩放目标尺寸
VIDEO_RESOLUTION    = "1080p"         # 视频分辨率（720p / 1080p）
VIDEO_RATIO         = "16:9"          # 视频画面比例（16:9 / 9:16 / 1:1）


def _resize_image(src_path: str, dst_path: str, target_size: tuple):
    """将图片缩放为目标尺寸（等比缩放，非裁剪，保留全部内容）"""
    with Image.open(src_path) as img:
        # LANCZOS 是高质量缩小算法
        resized = img.resize(target_size, Image.LANCZOS)
        resized.save(dst_path, quality=95)
    print(f"【图片缩放】{src_path} → {dst_path}  ({target_size[0]}x{target_size[1]})")


# ====================== 1. 文案生成（单次） ======================
def generate_copy(prompt: str) -> str:
    """豆包大模型生成文案，自动统计费用，返回文案文本。"""
    resp = ark_client.chat.completions.create(
        model=CHAT_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1024
    )
    content = resp.choices[0].message.content.strip()
    print("【文案生成结果】\n", content)

    usage = getattr(resp, "usage", None)
    if usage:
        prompt_tokens     = getattr(usage, "prompt_tokens",
                                   getattr(usage, "input_tokens", 0)) or 0
        completion_tokens = getattr(usage, "completion_tokens",
                                   getattr(usage, "output_tokens", 0)) or 0
        cost = prompt_tokens / 1000 * CHAT_INPUT_PRICE \
             + completion_tokens / 1000 * CHAT_OUTPUT_PRICE
        detail = (f"输入 {prompt_tokens} tokens × ¥{CHAT_INPUT_PRICE}/K，"
                  f"输出 {completion_tokens} tokens × ¥{CHAT_OUTPUT_PRICE}/K")
        tracker.add("文案生成", cost, detail)
    else:
        tracker.add("文案生成", 0.0, "响应中无 usage 信息")

    return content


# ====================== 1b. 分镜生成（主题 → 分镜列表） ======================
def generate_storyboard(topic: str, shot_count: int = None) -> list:
    """
    输入主题，调用大模型生成分镜描述列表。
    shot_count=None 时由 AI 根据内容自行决定分镜数量（如诗词全文、产品卖点等）。
    返回: [{"index": int, "subtitle": str, "image_prompt": str, "video_prompt": str}, ...]
    """
    if shot_count is not None:
        count_hint = f"请生成 {shot_count} 个分镜。"
    else:
        count_hint = ("请根据主题内容自行决定分镜数量。"
                      "如果是诗词/文章，请按每个自然句或段落一个分镜，确保全文覆盖；"
                      "如果是产品/知识主题，请覆盖所有关键卖点或知识点，通常 4-8 个分镜。")

    prompt = f"""你是一个短视频导演兼编剧。根据主题「{topic}」创作引人入胜的分镜脚本。
{count_hint}

═══ 核心创作原则 ═══
1. 讲故事，不要念说明书。用场景、细节、情感推动叙事，而非罗列卖点。
2. 文案是对话，不是口号。像朋友分享一样自然真诚，有温度、有呼吸感。
3. 分镜间要有叙事推进——铺垫→展开→高潮→余味，像故事章节层层递进。
4. 杜绝AI套话：禁用"颠覆""开启""燃爆""超乎想象""无限可能"等空洞词汇。
   用具体画面代替抽象概念，用真实情绪代替夸张修辞。

═══ 字幕文案规范 ═══
- 长短自如，该短则短该长则长，不刻意压缩也不刻意拉长
- 风格：像脱口秀旁白或朋友聊天，自然有停顿感，可以做留白
- 结构：开头钩子→中间展开→结尾金句，每一句都是前一句的延伸
- 反面示例（禁止）："XX来了！""重新定义XX""开启XX新时代""极致XX体验"
- 正面示例："他放下手机，抬头看了一眼窗外。天已经亮了。"

═══ 视觉风格统一（重要！） ═══
所有分镜的 image_prompt 必须共享统一的视觉风格体系：
- 统一画风：根据主题气质选定一种（如电影感写实/温暖日系/赛博科技感/水墨意境等），
  所有分镜的 image_prompt 开头都使用 SAME 画风描述
- 统一色调：贯穿始终的色调关键词（如 warm golden tones / cool cyan & navy 等）
- 统一光影：一致的光线方向和氛围（如 soft cinematic rim light / golden hour 等）
- 统一情绪：所有画面遵循相同的情绪基调

image_prompt 格式要求（英文）：
"画风描述 + 具体场景构图 + 色调光影 + 统一风格标记 + 构图比例 16:9, cinematic quality"
所有 image_prompt 的「画风描述」部分必须完全相同。

═══ 输出格式 ═══
严格按以下 JSON 数组输出，不要任何其他内容：
[
  {{"subtitle": "...", "image_prompt": "...", "video_prompt": "..."}},
  ...
]
"""
    resp = ark_client.chat.completions.create(
        model=CHAT_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_tokens=3072
    )
    content = resp.choices[0].message.content.strip()

    # 费用统计
    usage = getattr(resp, "usage", None)
    if usage:
        prompt_tokens     = getattr(usage, "prompt_tokens",
                                   getattr(usage, "input_tokens", 0)) or 0
        completion_tokens = getattr(usage, "completion_tokens",
                                   getattr(usage, "output_tokens", 0)) or 0
        cost = prompt_tokens / 1000 * CHAT_INPUT_PRICE \
             + completion_tokens / 1000 * CHAT_OUTPUT_PRICE
        detail = f"分镜生成 {prompt_tokens}+{completion_tokens} tokens"
        tracker.add("分镜生成", cost, detail)

    # 解析 JSON（兼容代码块包裹的情况）
    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        storyboard = json.loads(content.strip())
        for i, shot in enumerate(storyboard):
            shot["index"] = i + 1
        print(f"【分镜生成成功】共 {len(storyboard)} 个分镜")
        for shot in storyboard:
            print(f"  分镜{shot['index']}：{shot['subtitle']}")
        return storyboard
    except Exception as e:
        print(f"⚠️  分镜 JSON 解析失败：{e}")
        print("原始返回：", content[:500])
        return []


# ====================== 2. 语音合成 TTS（单次） ======================
def text_to_speech(text: str, save_path: str,
                   voice: str = None) -> str | None:
    """火山大模型语音合成（V3 接口），返回保存路径或 None。"""
    if not TTS_APP_ID or not TTS_ACCESS_TOKEN:
        print(f"【TTS 跳过】{save_path}：未配置 TTS_APP_ID / TTS_ACCESS_TOKEN")
        return None
    voice = voice or TTS_VOICE
    url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    headers = {
        "Content-Type": "application/json",
        "X-Api-App-Id": TTS_APP_ID,
        "X-Api-Access-Key": TTS_ACCESS_TOKEN,
        "X-Api-Resource-Id": TTS_CLUSTER,
    }
    payload = {
        "user": {"uid": "user_001"},
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": {"format": "mp3", "sample_rate": 24000}
        }
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        print(f"TTS HTTP 失败: {resp.status_code}, {resp.text[:200]}")
        return None

    audio_chunks = []
    for line in resp.text.strip().split("\n"):
        try:
            d = json.loads(line)
            code = d.get("code", -1)
            if code == 0 and d.get("data"):
                audio_chunks.append(base64.b64decode(d["data"]))
            elif code not in (0, 20000000):
                print(f"TTS 错误: code={code}, {d.get('message', '')}")
                return None
        except json.JSONDecodeError:
            pass

    if not audio_chunks:
        print(f"TTS 未返回音频数据：{text[:30]}...")
        return None

    full_audio = b"".join(audio_chunks)
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(full_audio)
    print(f"【TTS】{os.path.basename(save_path)} ({len(full_audio)} bytes)")

    # 费用统计
    char_count = len(text)
    cost = char_count / 10000 * TTS_PRICE_PER_10K
    tracker.add(f"TTS-分镜", cost, f"{char_count}字符 × ¥{TTS_PRICE_PER_10K}/万")
    return save_path


# ====================== 2b. 批量 TTS（并发） ======================
def batch_text_to_speech(texts: list[str],
                         save_dir: str = None,
                         voice: str = None) -> list[str]:
    """并发生成多段语音，返回路径列表（失败项为 None）。"""
    save_dir = save_dir or os.path.join(SCRIPT_DIR, "audio")
    os.makedirs(save_dir, exist_ok=True)

    def _worker(i_text):
        i, text = i_text
        path = os.path.join(save_dir, f"audio_{i:02d}.mp3")
        return i, text_to_speech(text, save_path=path, voice=voice)

    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=min(len(texts), 4)) as ex:
        futures = {ex.submit(_worker, (i, t)): i for i, t in enumerate(texts)}
        for fut in as_completed(futures):
            i, path = fut.result()
            results[i] = path
    return results


# ====================== 3. 文生图（单次） ======================
def text_to_image(prompt: str, save_path: str) -> str | None:
    """文生图，下载后缩放为 1920x1080，返回保存路径或 None。"""
    try:
        resp = ark_client.images.generate(
            model=IMAGE_MODEL_ID,
            prompt=prompt,
            size=IMAGE_GEN_SIZE   # 2560x1440（满足最低像素要求）
        )
        img_url = resp.data[0].url
        print(f"【文生图】{os.path.basename(save_path)}：{img_url[:60]}...")
    except Exception as e:
        print(f"文生图 API 失败：{e}")
        return None

    img_resp = requests.get(img_url, timeout=60)
    if img_resp.status_code != 200:
        print(f"图片下载失败：{img_resp.status_code}")
        return None

    # 先保存原始图片
    tmp_path = save_path + ".tmp.png"
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    with open(tmp_path, "wb") as f:
        f.write(img_resp.content)
    print(f"【图片下载完成】原始 {tmp_path} ({len(img_resp.content)} bytes)")

    # 缩放到目标尺寸
    _resize_image(tmp_path, save_path, IMAGE_TARGET_SIZE)
    os.remove(tmp_path)

    tracker.add(f"文生图-分镜", IMAGE_PRICE,
                 f"固定单价 ¥{IMAGE_PRICE}/张（输出 {IMAGE_TARGET_SIZE[0]}x{IMAGE_TARGET_SIZE[1]}）")
    return save_path


# ====================== 3b. 批量文生图（并发） ======================
def batch_text_to_image(prompts: list[str],
                       save_dir: str = None) -> list[str]:
    """并发生成多张图片，返回路径列表（失败项为 None）。"""
    save_dir = save_dir or os.path.join(SCRIPT_DIR, "images")
    os.makedirs(save_dir, exist_ok=True)

    def _worker(i_prompt):
        i, prompt = i_prompt
        path = os.path.join(save_dir, f"image_{i:02d}.png")
        return i, text_to_image(prompt, save_path=path)

    results = [None] * len(prompts)
    with ThreadPoolExecutor(max_workers=min(len(prompts), 4)) as ex:
        futures = {ex.submit(_worker, (i, p)): i for i, p in enumerate(prompts)}
        for fut in as_completed(futures):
            i, path = fut.result()
            results[i] = path
    return results


# ====================== 4. 文生视频（单次，异步） ======================
def text_to_video(prompt: str, save_path: str,
                  poll_interval: int = 10) -> str | None:
    """文生视频：提交任务 + 轮询，返回保存路径或 None。"""
    try:
        create_resp = ark_client.content_generation.tasks.create(
            model=VIDEO_MODEL_ID,
            content=[{"type": "text", "text": prompt}],
            resolution=VIDEO_RESOLUTION,
            ratio=VIDEO_RATIO,
        )
        task_id = create_resp.id
        print(f"【视频任务】{os.path.basename(save_path)}  TaskID: {task_id}")
    except Exception as e:
        print(f"视频任务提交失败：{e}")
        return None

    while True:
        time.sleep(poll_interval)
        query_resp = ark_client.content_generation.tasks.get(task_id=task_id)
        status = query_resp.status
        print(f"  视频任务 {task_id} 状态：{status}")

        if status == "succeeded":
            video_url = query_resp.content.video_url
            v_resp = requests.get(video_url, timeout=120)
            if v_resp.status_code == 200:
                os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(v_resp.content)
                print(f"【视频下载完成】{save_path} ({len(v_resp.content)} bytes)")

                # 费用统计
                has_audio    = getattr(query_resp, "generate_audio", True)
                unit_price   = VIDEO_PRICE_AUDIO if has_audio else VIDEO_PRICE_SILENT
                usage        = getattr(query_resp, "usage", None)
                total_tokens = getattr(usage, "completion_tokens",
                                       getattr(usage, "total_tokens", 0)) if usage else 0
                if total_tokens:
                    cost = total_tokens / 1_000_000 * unit_price
                    detail = f"{'有声' if has_audio else '无声'}视频 {total_tokens} tokens"
                else:
                    cost = unit_price
                    detail = f"{'有声' if has_audio else '无声'}视频（无 usage）"
                tracker.add(f"文生视频-分镜", cost, detail)
                return save_path
            else:
                print(f"视频下载失败：{v_resp.status_code}")
                return None

        elif status in ("failed", "cancelled"):
            print(f"视频任务失败：{getattr(query_resp, 'error', '')}")
            return None


# ====================== 4b. 批量文生视频（并发提交 + 分别轮询） ======================
def batch_text_to_video(prompts: list[str],
                        save_dir: str = None) -> list[str]:
    """并发提交多个视频生成任务，分别轮询，返回视频路径列表（失败项为 None）。"""
    save_dir = save_dir or os.path.join(SCRIPT_DIR, "videos")
    os.makedirs(save_dir, exist_ok=True)

    def _worker(i_prompt):
        i, prompt = i_prompt
        path = os.path.join(save_dir, f"video_{i:02d}.mp4")
        return i, text_to_video(prompt, save_path=path)

    results = [None] * len(prompts)
    with ThreadPoolExecutor(max_workers=min(len(prompts), 2)) as ex:
        futures = {ex.submit(_worker, (i, p)): i for i, p in enumerate(prompts)}
        for fut in as_completed(futures):
            i, path = fut.result()
            results[i] = path
    return results


# ====================== 总入口：主题 → 完整素材包 ======================
def generate_media_pack(topic: str,
                        shot_count: int = None,
                        mode: str = "image",
                        save_dir: str = None) -> dict:
    """
    输入主题，自动生成分镜 + 音频 + 图片/视频素材包。

    :param topic:       主题，如「量子力学」「再别康桥」
    :param shot_count:  分镜数量（None=AI自动决定，如诗词全文输出）
    :param mode:        "image" 生成图片，"video" 生成视频
    :param save_dir:    输出根目录（默认脚本目录下 output/{topic}/）
    :return: {
        "topic": str,
        "storyboard": [{"index", "subtitle", "image_prompt", "video_prompt"}],
        "audio_paths": [str|None],
        "media_paths": [str|None],
        "elapsed_seconds": float,
    }
    """
    print("\n" + "=" * 60)
    count_label = f"{shot_count}" if shot_count else "AI自动"
    print(f"  🎬 开始生成素材包 — 主题：「{topic}」 分镜数：{count_label}  模式：{mode}")
    print("=" * 60)

    t_start = time.time()

    # 1. 生成分镜
    storyboard = generate_storyboard(topic, shot_count=shot_count)
    if not storyboard:
        print("❌ 分镜生成失败，终止。")
        return {"topic": topic, "storyboard": [], "audio_paths": [], "media_paths": []}

    # 准备输出目录
    safe_topic = "".join(c for c in topic if c.isalnum() or c in "＿_ -").strip()
    out_dir = save_dir or os.path.join(SCRIPT_DIR, "output", safe_topic)
    audio_dir = os.path.join(out_dir, "audio")
    media_dir = os.path.join(out_dir, "images" if mode == "image" else "videos")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(media_dir, exist_ok=True)

    # 提取字幕列表和 prompt 列表
    subtitles   = [s["subtitle"] for s in storyboard]
    img_prompts = [s["image_prompt"] for s in storyboard]
    vid_prompts = [s["video_prompt"] for s in storyboard]

    # 2. 并发生成音频
    print(f"\n🎤 开始并发生成 {len(subtitles)} 段语音...")
    audio_paths = batch_text_to_speech(subtitles, save_dir=audio_dir)

    # 3. 并发生成图片或视频
    if mode == "image":
        print(f"\n🖼️  开始并发生成 {len(img_prompts)} 张图片（输出尺寸 {IMAGE_TARGET_SIZE[0]}x{IMAGE_TARGET_SIZE[1]}）...")
        media_paths = batch_text_to_image(img_prompts, save_dir=media_dir)
    else:
        print(f"\n🎥 开始并发生成 {len(vid_prompts)} 段视频（{VIDEO_RESOLUTION} {VIDEO_RATIO}）...")
        media_paths = batch_text_to_video(vid_prompts, save_dir=media_dir)

    # 汇总
    elapsed = time.time() - t_start
    result = {
        "topic": topic,
        "storyboard":  storyboard,
        "audio_paths": audio_paths,
        "media_paths": media_paths,
        "elapsed_seconds": round(elapsed, 1),
    }

    print("\n" + "=" * 60)
    print(f"  ✅ 素材包生成完成 — 输出目录：{out_dir}")
    print("=" * 60)
    for i, shot in enumerate(storyboard):
        a_ok = "✅" if audio_paths[i] else "❌"
        m_ok = "✅" if media_paths[i] else "❌"
        print(f"  分镜{i+1:02d}  {a_ok}音频  {m_ok}媒体  「{shot['subtitle']}」")
    print()

    tracker.summary()

    # 用时
    mins, secs = divmod(elapsed, 60)
    if mins >= 1:
        time_str = f"{int(mins)}分{secs:.0f}秒"
    else:
        time_str = f"{secs:.1f}秒"
    print(f"\n⏱️  总用时：{time_str}")

    return result


# ====================== 主函数（示例） ======================
if __name__ == "__main__":
    # 示例：生成「量子力学」主题素材包（图片模式，输出 1920x1080）
    result = generate_media_pack(
        topic="薛定谔的猫",
        shot_count=2,
        mode="video",
    )

    # 打印结构化输出
    print("\n📦 结构化输出：")
    print("字幕文本列表：", [s["subtitle"] for s in result["storyboard"]])
    print("音频文件路径列表：", result["audio_paths"])
    print("媒体文件路径列表：", result["media_paths"])
