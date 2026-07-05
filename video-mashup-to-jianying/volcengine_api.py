"""
混剪素材生成模块
功能：本地视频文件夹 → 随机抽选 → AI视频理解 → 卖货文案生成 → TTS音频
依赖：volcenginesdkarkruntime, python-dotenv, requests, opencv-python-headless, Pillow
"""

import os
import time
import base64
import random
import requests
import json
import cv2
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark
from concurrent.futures import ThreadPoolExecutor, as_completed

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


# 视觉理解模型单价（元/千tokens）
VISION_INPUT_PRICE  = _float_env("VISION_INPUT_PRICE",  0.003)
VISION_OUTPUT_PRICE = _float_env("VISION_OUTPUT_PRICE", 0.009)
# TTS 单价
TTS_PRICE_PER_10K = _float_env("TTS_PRICE_PER_10K", 5.0)
# 文本模型单价（元/千tokens）— 用于连贯文案生成
CHAT_INPUT_PRICE  = _float_env("CHAT_INPUT_PRICE",  0.0008)
CHAT_OUTPUT_PRICE = _float_env("CHAT_OUTPUT_PRICE", 0.002)


# ====================== 全局配置 ======================
ARK_API_KEY = os.getenv("ARK_API_KEY")
VOLC_REGION = os.getenv("VOLC_REGION", "cn-beijing")

# 视觉理解模型（用于视频画面分析 + 卖货文案生成）
VISION_MODEL_ID = os.getenv("VISION_MODEL_ID", "doubao-1.5-vision-pro-32k-250115")

# 文本模型（用于兜底文案生成）
CHAT_MODEL_ID  = os.getenv("CHAT_MODEL_ID")

TTS_APP_ID       = os.getenv("TTS_APP_ID")
TTS_ACCESS_TOKEN = os.getenv("TTS_ACCESS_TOKEN")
TTS_CLUSTER      = os.getenv("TTS_CLUSTER", "volc.service_type.10029")
TTS_VOICE        = os.getenv("TTS_VOICE", "zh_female_kailangjiejie_uranus_bigtts")
# V3 接口语速参数 speech_rate: [-50, 100], 0=1.0倍速, 100=2.0倍速, -50=0.5倍速
# 公式: speech_rate = (目标倍速 - 1.0) * 100，如 1.25倍速 → 25
TTS_SPEECH_RATE  = int(os.getenv("TTS_SPEECH_RATE", "25"))
# 2.0 音色(uranus_bigtts)需使用 seed-tts-2.0 资源ID, 1.0 音色(moon/mars_bigtts)用 volc.service_type.10029
TTS_RESOURCE_ID  = os.getenv("TTS_RESOURCE_ID", "seed-tts-2.0")

if not ARK_API_KEY:
    raise ValueError("请在 .env 文件中配置 ARK_API_KEY")
ark_client = Ark(api_key=ARK_API_KEY, region=VOLC_REGION)


# ====================== 支持的视频扩展名 ======================
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}


# ====================== 1. 扫描文件夹中的视频文件 ======================
def scan_video_files(folder_path: str) -> list[str]:
    """扫描文件夹中的所有视频文件，返回完整路径列表。"""
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"文件夹路径不存在: {folder_path}")

    video_files = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                video_files.append(os.path.join(root, f))

    return video_files


# ====================== 1b. 获取视频时长（秒） ======================
def get_video_duration(video_path: str) -> float:
    """返回视频时长（秒）。失败返回 0.0。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    cap.release()
    if fps <= 0 or total_frames <= 0:
        return 0.0
    return round(total_frames / fps, 2)


# ====================== 目标字数计算 ======================
# 语速参考：普通口播 4字/秒；1.25倍速下 ≈ 5字/秒
# 加上 TTS 前后各约 0.3 秒的静音余量，实际目标字数按 4.5 字/秒稍留裕度
def calc_target_chars(duration_seconds: float, speech_rate: int = None,
                      min_chars: int = 12, max_chars: int = 60) -> int:
    """
    根据视频时长和 TTS 语速倍率，估算目标口播字数。
    :param duration_seconds: 视频时长（秒）
    :param speech_rate: TTS 语速参数 [-50, 100]，None 表示读取全局 TTS_SPEECH_RATE
    :param min_chars: 最少字数（避免过短片段生成难以启齿的短句）
    :param max_chars: 最多字数（避免超长视频生成又臭又长的文案，超长部分靠视频裁剪处理）
    :return: 目标字数
    """
    if speech_rate is None:
        speech_rate = TTS_SPEECH_RATE
    multiplier = 1.0 + speech_rate / 100  # 25 → 1.25 倍
    # 每秒字数：基准 4 字/秒 × 倍率
    chars_per_sec = 4.0 * multiplier
    # 减去 0.5 秒余量（首尾静音+段间过渡）
    effective_sec = max(duration_seconds - 0.5, 1.0)
    raw = int(effective_sec * chars_per_sec)
    return max(min(raw, max_chars), min_chars)


# ====================== 2. 从视频中抽取关键帧 ======================
def extract_frames(video_path: str, num_frames: int = 4,
                   max_size: int = 768) -> list[str]:
    """
    从视频中均匀抽取关键帧，返回 base64 编码的 JPEG 列表。
    :param video_path: 视频文件路径
    :param num_frames: 抽取帧数
    :param max_size: 帧的最大边长（像素），用于压缩以减少 token 消耗
    :return: base64 编码的 JPEG 字符串列表
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  ⚠️  无法打开视频: {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return []

    frames = []
    for i in range(num_frames):
        # 均匀分布取帧（避开开头和结尾）
        frame_idx = int(total_frames * (i + 0.5) / num_frames)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # 缩放到 max_size 以内
        h, w = frame.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        # 编码为 JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buffer).decode('utf-8')
        frames.append(b64)

    cap.release()
    return frames


# ====================== 3. 视频画面理解（仅分析，不写文案） ======================
def analyze_video_only(
    video_path: str,
    index: int = 0,
    frame_count: int = 4,
) -> dict:
    """
    对单个视频进行画面理解，返回画面描述（不生成文案）。
    文案将在 Phase 2 统一生成以保证连贯性。

    :param video_path: 视频文件路径
    :param index: 序号（用于日志）
    :param frame_count: 抽取帧数
    :return: {
        "index": int,
        "video_path": str,
        "video_analysis": str,   # 视频画面描述
        "frames_extracted": int,
    }
    """
    video_name = os.path.basename(video_path)
    duration = get_video_duration(video_path)
    print(f"  🎬 [{index+1}] 分析视频画面: {video_name} ({duration}秒)")

    # 1. 抽取关键帧
    frames_b64 = extract_frames(video_path, num_frames=frame_count)
    if not frames_b64:
        print(f"  ❌ [{index+1}] 帧抽取失败")
        return {
            "index": index,
            "video_path": video_path,
            "duration": duration,
            "video_analysis": "无法分析视频画面",
            "frames_extracted": 0,
        }

    # 2. 构建视觉理解 prompt（只分析画面，不写文案）
    prompt = """请仔细观看以下视频画面截图（按时间顺序排列），用1-2句话准确描述视频画面展示了什么内容、场景或产品使用过程。

只输出描述内容，不要加任何前缀或解释。"""

    # 3. 构建多模态消息内容
    content = [{"type": "text", "text": prompt}]
    for b64 in frames_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    # 4. 调用视觉模型
    try:
        resp = ark_client.chat.completions.create(
            model=VISION_MODEL_ID,
            messages=[{"role": "user", "content": content}],
            temperature=0.3,
            max_tokens=256
        )
        raw = resp.choices[0].message.content.strip()

        # 费用统计
        usage = getattr(resp, "usage", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens",
                                    getattr(usage, "input_tokens", 0)) or 0
            completion_tokens = getattr(usage, "completion_tokens",
                                        getattr(usage, "output_tokens", 0)) or 0
            cost = prompt_tokens / 1000 * VISION_INPUT_PRICE \
                 + completion_tokens / 1000 * VISION_OUTPUT_PRICE
            detail = f"视觉理解 {prompt_tokens}+{completion_tokens} tokens ({len(frames_b64)}帧)"
            tracker.add(f"视频理解-片段{index+1}", cost, detail)

        video_analysis = raw.strip() if raw else "无法分析视频画面"

        print(f"  ✅ [{index+1}] 画面: {video_analysis[:60]}...")

        return {
            "index": index,
            "video_path": video_path,
            "duration": duration,
            "video_analysis": video_analysis,
            "frames_extracted": len(frames_b64),
        }

    except Exception as e:
        print(f"  ❌ [{index+1}] 视觉理解失败: {e}")
        return {
            "index": index,
            "video_path": video_path,
            "duration": duration,
            "video_analysis": "理解失败",
            "frames_extracted": len(frames_b64),
        }


# ====================== 3b. 连贯文案脚本生成（Phase 2） ======================
def generate_coherent_script(
    analyses: list[dict],
    product_desc: str,
) -> list[str]:
    """
    根据所有视频的画面分析结果，生成一段连贯的卖货文案脚本。
    整体像一个主播从头讲到尾，有起承转合，每段对应一个视频片段。

    :param analyses: batch_analyze_videos Phase 1 的结果列表
    :param product_desc: 产品卖点描述
    :return: 每个片段对应的文案列表
    """
    n = len(analyses)
    print(f"\n🧠 Phase 2: 生成连贯卖货脚本（{n}段，产品：{product_desc}）...")

    # 计算每段目标字数（按视频时长动态分配，保证音视频对齐）
    target_chars_list = []
    for a in analyses:
        d = a.get("duration", 0) or 0
        target = calc_target_chars(d)
        target_chars_list.append(target)

    # 拼接所有视频的画面分析 + 每段目标字数约束
    analyses_text = ""
    for i, a in enumerate(analyses):
        d = a.get("duration", 0) or 0
        target = target_chars_list[i]
        low = max(target - 3, 5)
        high = target + 3
        analyses_text += (
            f"片段{a['index']+1}（视频时长{d}秒，目标{low}-{high}字）: "
            f"{a['video_analysis']}\n"
        )

    total_target = sum(target_chars_list)
    total_duration = sum((a.get("duration", 0) or 0) for a in analyses)

    prompt = f"""你是一个专业的短视频带货编剧。

【产品信息】{product_desc}

【视频素材分析】
以下是{n}个视频片段的画面分析，这些片段将按顺序拼接成一个完整的卖货视频。
**每个片段都标注了对应视频的实际时长和目标字数区间**，你必须严格按目标字数生成对应文案：

{analyses_text}

总时长约 {total_duration:.1f} 秒，总字数目标约 {total_target} 字。

【任务】
请为这{n}个视频片段分别写一段口播文案，组合起来构成一个连贯的卖货视频脚本。

【文案要求】
- ⚠️ **字数严格约束**：每段文案必须落在标注的目标区间内（如"目标18-24字"，请生成21字左右）。这是硬性要求，因为音频将与视频等长播放。
- 每段文案的核心内容必须严格对应【视频素材分析】中该片段的具体画面描述，**看到什么说什么**：该片段的分析写了什么，文案就围绕什么展开，不要跑题到其他片段的内容上
- **禁止将其他片段画面的卖点硬塞到本段文案中**——画面没展示的内容，这段文案绝对不要提
- 各段之间的连贯性通过叙事语气（如"看这里""接下来""最后"）和过渡词实现，不要求每段覆盖产品所有卖点
- 整体像一个主播从头讲到尾，有起承转合的自然节奏
- 第一段要能吸引注意力、引出产品
- 最后一段要有行动号召或温暖总结
- 自然口语化，像朋友推荐好物，不要播音腔
- 杜绝"颠覆""燃爆""超乎想象"等AI套话
- 段与段之间要有自然的过渡衔接，不要生硬拼接
- 如果某段目标字数很少（≤12字），就用一个短句/感叹讲清一个亮点；如果目标很多（≥40字），可用两句话展开细节

【输出格式】
严格输出JSON数组，不要任何其他内容：
[
  {{"segment": 1, "sales_copy": "第一段文案..."}},
  {{"segment": 2, "sales_copy": "第二段文案..."}}
]"""

    model_to_use = CHAT_MODEL_ID or VISION_MODEL_ID

    try:
        resp = ark_client.chat.completions.create(
            model=model_to_use,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=2048,
        )
        raw = resp.choices[0].message.content.strip()

        # 费用统计
        usage = getattr(resp, "usage", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens",
                                    getattr(usage, "input_tokens", 0)) or 0
            completion_tokens = getattr(usage, "completion_tokens",
                                        getattr(usage, "output_tokens", 0)) or 0
            if model_to_use == CHAT_MODEL_ID:
                input_price = CHAT_INPUT_PRICE
                output_price = CHAT_OUTPUT_PRICE
            else:
                input_price = VISION_INPUT_PRICE
                output_price = VISION_OUTPUT_PRICE
            cost = prompt_tokens / 1000 * input_price \
                 + completion_tokens / 1000 * output_price
            detail = f"文本生成 {prompt_tokens}+{completion_tokens} tokens ({n}段连贯脚本)"
            tracker.add("连贯文案生成", cost, detail)

        # 解析 JSON（增强健壮性：处理 ```json 包裹、前后杂文、截取数组）
        result_text = raw.strip()
        # 去除 markdown 代码块包裹
        if "```" in result_text:
            # 找到第一个 ``` 后面的内容
            parts = result_text.split("```")
            # parts[1] 通常是 json\n{...} 或 直接 {...}
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("[") or p.startswith("{"):
                    result_text = p
                    break
        # 兜底：截取从第一个 [ 到最后一个 ] 之间的内容
        if not result_text.startswith("["):
            l = result_text.find("[")
            r = result_text.rfind("]")
            if l >= 0 and r > l:
                result_text = result_text[l:r+1]

        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError as je:
            print(f"⚠️  JSON 解析失败，尝试宽松修复：{je}")
            # 尝试修复常见问题：单引号、尾逗号
            fixed = result_text.replace("'", '"')
            # 去除对象末尾多余逗号
            import re as _re
            fixed = _re.sub(r",\s*([\]}])", r"\1", fixed)
            parsed = json.loads(fixed)

        # 按 segment 序号提取文案
        copies = []
        for i in range(n):
            found = False
            for item in parsed:
                if item.get("segment") == i + 1:
                    copies.append(item.get("sales_copy", ""))
                    found = True
                    break
            if not found:
                copies.append(f"今天给大家推荐{product_desc}，真的很好用！")

        print(f"✅ 连贯文案生成完成：")
        for i, c in enumerate(copies):
            actual = len(c)
            target = target_chars_list[i] if i < len(target_chars_list) else 0
            match = "✅" if abs(actual - target) <= 5 else "⚠️"
            d = analyses[i].get("duration", 0) or 0
            print(f"  片段{i+1} ({d}秒/目标{target}字/实际{actual}字){match}: {c}")

        return copies

    except Exception as e:
        print(f"❌ 连贯文案生成失败: {e}")
        # 兜底：每段独立文案
        return [f"今天给大家推荐{product_desc}，真的很好用，试试就知道！" for _ in range(n)]


# ====================== 3c. 批量视频分析 + 连贯文案生成（两阶段） ======================
def batch_analyze_videos(
    video_paths: list[str],
    product_desc: str,
    frame_count: int = 4,
) -> list[dict]:
    """
    两阶段处理：
    Phase 1: 并发分析所有视频画面（只描述，不写文案）
    Phase 2: 汇总所有画面分析，一次性生成连贯卖货脚本

    返回分析结果列表（按原始顺序排列），每个结果包含 video_analysis 和 sales_copy。
    """
    # Phase 1: 并发分析视频画面
    print(f"\n🧠 Phase 1: 并发分析 {len(video_paths)} 个视频画面...")
    results = [None] * len(video_paths)

    def _worker(idx_video):
        idx, vpath = idx_video
        return idx, analyze_video_only(
            video_path=vpath,
            frame_count=frame_count,
            index=idx,
        )

    max_workers = min(len(video_paths), 3)  # 视觉模型并发不宜太高
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_worker, (i, v)): i for i, v in enumerate(video_paths)}
        for fut in as_completed(futures):
            idx, result = fut.result()
            results[idx] = result

    # Phase 2: 汇总画面分析，生成连贯文案脚本
    sales_copies = generate_coherent_script(results, product_desc)

    # 合并文案到结果中
    for i, r in enumerate(results):
        r["sales_copy"] = sales_copies[i] if i < len(sales_copies) \
            else f"今天给大家推荐{product_desc}！"

    return results


# ====================== 4. 语音合成 TTS（单次） ======================
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
        "X-Api-Resource-Id": TTS_RESOURCE_ID,
    }
    audio_params = {"format": "mp3", "sample_rate": 24000}
    if TTS_SPEECH_RATE != 0:
        audio_params["speech_rate"] = TTS_SPEECH_RATE
    payload = {
        "user": {"uid": "user_001"},
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": audio_params,
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
    tracker.add(f"TTS-片段", cost, f"{char_count}字符 × ¥{TTS_PRICE_PER_10K}/万")
    return save_path


# ====================== 4b. 批量 TTS（并发） ======================
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


# ====================== 总入口：混剪素材包生成 ======================
def generate_mashup_pack(
    folder_path: str,
    product_desc: str,
    video_count: int = 6,
    frame_count: int = 4,
    voice: str = None,
    save_dir: str = None,
) -> dict:
    """
    混剪素材包生成主入口。

    :param folder_path:  本地视频文件夹路径
    :param product_desc: 产品卖点描述，如"清风卫生纸，柔然又好用"
    :param video_count:  随机抽选视频数量
    :param frame_count:  每个视频抽取的帧数（用于AI理解）
    :param voice:        TTS音色（None=使用.env默认）
    :param save_dir:     输出根目录（默认脚本目录下 output/mashup_{timestamp}/）
    :return: {
        "product_desc": str,
        "video_paths": [str],          # 选中的视频路径
        "storyboard": [{index, video_analysis, sales_copy, video_path}],
        "audio_paths": [str|None],
        "media_paths": [str],           # = video_paths
        "subtitle_texts": [str],        # = sales_copy 列表
        "elapsed_seconds": float,
    }
    """
    print("\n" + "=" * 60)
    print(f"  🎬 混剪素材包生成 — 产品：「{product_desc}」")
    print(f"  📁 视频文件夹：{folder_path}")
    print(f"  🎞️  抽选数量：{video_count}  帧数/视频：{frame_count}")
    print("=" * 60)

    t_start = time.time()

    # 1. 扫描文件夹
    all_videos = scan_video_files(folder_path)
    print(f"\n📂 扫描到 {len(all_videos)} 个视频文件")

    if len(all_videos) == 0:
        print("❌ 文件夹中没有视频文件，终止。")
        return None

    # 2. 随机抽选
    actual_count = min(video_count, len(all_videos))
    if actual_count < video_count:
        print(f"  ⚠️  文件夹只有 {len(all_videos)} 个视频，全部使用。")
    selected_videos = random.sample(all_videos, actual_count)
    print(f"🎲 随机抽选了 {actual_count} 个视频：")
    for i, v in enumerate(selected_videos):
        print(f"  {i+1}. {os.path.basename(v)}")

    # 3. 准备输出目录
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in product_desc[:10] if c.isalnum() or c in "＿_ -").strip()
    out_dir = save_dir or os.path.join(SCRIPT_DIR, "output", f"mashup_{safe_name}_{timestamp}")
    audio_dir = os.path.join(out_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    # 4. 并发：视频理解 + 文案生成
    print(f"\n🧠 开始并发分析 {actual_count} 个视频（视觉理解 + 文案生成）...")
    analysis_results = batch_analyze_videos(
        video_paths=selected_videos,
        product_desc=product_desc,
        frame_count=frame_count,
    )

    # 5. 提取文案列表
    storyboard = []
    subtitle_texts = []
    for r in analysis_results:
        if r is None:
            continue
        storyboard.append(r)
        subtitle_texts.append(r["sales_copy"])

    print(f"\n📝 文案生成完成，共 {len(subtitle_texts)} 段：")
    for i, text in enumerate(subtitle_texts):
        print(f"  片段{i+1}: {text}")

    # 6. 并发：TTS 音频生成
    print(f"\n🎤 开始并发生成 {len(subtitle_texts)} 段语音...")
    audio_paths = batch_text_to_speech(subtitle_texts, save_dir=audio_dir, voice=voice)

    # 7. 汇总
    elapsed = time.time() - t_start
    result = {
        "product_desc": product_desc,
        "video_paths": selected_videos[:len(storyboard)],
        "storyboard": storyboard,
        "audio_paths": audio_paths,
        "media_paths": [r["video_path"] for r in storyboard],
        "subtitle_texts": subtitle_texts,
        "elapsed_seconds": round(elapsed, 1),
    }

    # 打印汇总
    print("\n" + "=" * 60)
    print(f"  ✅ 混剪素材包生成完成 — 输出目录：{out_dir}")
    print("=" * 60)
    for i, shot in enumerate(storyboard):
        a_ok = "✅" if audio_paths[i] else "❌"
        v_ok = "✅"
        print(f"  片段{i+1:02d}  {a_ok}音频  {v_ok}视频  「{shot['sales_copy'][:30]}...」")
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
    result = generate_mashup_pack(
        folder_path=r"C:\Users\13251\Videos\product_videos",
        product_desc="清风卫生纸，柔然又好用",
        video_count=6,
        frame_count=4,
    )

    if result:
        print("\n📦 结构化输出：")
        print("视频路径列表：", result["video_paths"])
        print("字幕文案列表：", result["subtitle_texts"])
        print("音频文件路径列表：", result["audio_paths"])
