# 使用此指令前，请确保安装必要的Python库，例如使用以下命令安装：
# pip install pyJianYingDraft Pillow

import os
import re
import random
import pyJianYingDraft as draft
from pyJianYingDraft import (TrackType, TextStyle, ClipSettings, TextBackground,
                             KeyframeProperty, trange)
from PIL import Image

def create_jianying_draft_with_media(draft_name, subtitle_texts, audio_paths, media_paths, draft_folder_path,
                                   add_image_movement=True, add_video_movement=True,
                                   split_subtitles=True, background_image=None, background_music=None,
                                   mute_original_video=True, crop_video=True):
    """
    title: jianying_draft_composer
    description: 根据 %subtitle_texts%、%audio_paths%、%media_paths% 创建剪映草稿，支持图片视频混合、运镜效果、背景图片和背景音乐，可选择是否将字幕拆分成短句并同步显示，支持对原视频静音处理和视频裁剪
    inputs:
        - draft_name (str): 草稿名称，eg: "我的视频草稿"
        - subtitle_texts (list): 字幕文本列表，eg: ["第一段字幕内容", "第二段字幕内容"]
        - audio_paths (list): 音频文件路径列表，eg: ["audio1.mp3", "audio2.wav"]
        - media_paths (list): 媒体文件路径列表（支持图片和视频混合），eg: ["image1.jpg", "video1.mp4"]
        - draft_folder_path (folder): 剪映草稿文件夹路径
        - add_image_movement (bool): 是否为图片添加随机运镜效果，默认True，eg: True
        - add_video_movement (bool): 是否为视频添加随机运镜效果，默认True，eg: True
        - split_subtitles (bool): 是否将字幕拆分成短句，默认True，eg: True
        - mute_original_video (bool): 是否对原视频进行静音处理，默认True（混剪场景通常静音原视频），eg: True
        - crop_video (bool): 是否对视频进行裁剪（音频短于视频时），默认True（混剪场景通常裁剪），eg: True
        - background_image (file): 背景图片路径_可为空，eg: "background.jpg"
        - background_music (file): 背景音乐路径_可为空，eg: "bgm.mp3"
    outputs:
        - result (str): 执行结果，eg: 剪映草稿 '我的视频项目' 创建成功！
    """

    def _split_subtitle(subtitle):
        """将字幕按指定标点符号拆分短句，保留标点符号在句尾"""
        separators = r'([，。！,!?；])'
        parts = re.split(separators, subtitle)

        sentences = []
        for i in range(0, len(parts)-1, 2):
            if parts[i] or parts[i+1]:  # 避免空字符串
                sentences.append(parts[i] + parts[i+1])

        # 处理可能剩余的部分（如果字幕不以标点结尾）
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1].strip())

        return sentences

    def _add_zoom_in(segment, duration):
        """从远到近（放大）"""
        segment.add_keyframe(KeyframeProperty.uniform_scale, 0, 1)
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=duration, value=1.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=duration, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=duration, value=0)

    def _add_zoom_out(segment, duration):
        """从近到远（缩小）"""
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=0, value=1.25)
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=duration, value=1)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=duration, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=duration, value=0)

    def _add_move_up(segment, duration):
        """从下到上"""
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=0, value=1.25)
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=duration, value=1.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=duration, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=0, value=-0.25)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=duration, value=0.25)

    def _add_move_down(segment, duration):
        """从上到下"""
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=0, value=1.25)
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=duration, value=1.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=duration, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=0, value=0.25)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=duration, value=-0.25)

    def _add_move_left(segment, duration):
        """从右到左"""
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=0, value=1.25)
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=duration, value=1.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=0, value=-0.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=duration, value=0.25)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=duration, value=0)

    def _add_move_right(segment, duration):
        """从左到右"""
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=0, value=1.25)
        segment.add_keyframe(KeyframeProperty.uniform_scale, time_offset=duration, value=1.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=0, value=0.25)
        segment.add_keyframe(KeyframeProperty.position_x, time_offset=duration, value=-0.25)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=0, value=0)
        segment.add_keyframe(KeyframeProperty.position_y, time_offset=duration, value=0)

    # 运镜效果列表
    camera_effects = [
        _add_zoom_in, _add_zoom_out, _add_move_up,
        _add_move_down, _add_move_left, _add_move_right
    ]

    # 校验输入参数
    if not isinstance(draft_name, str) or not draft_name.strip():
        raise ValueError("草稿名称不能为空")

    if not isinstance(subtitle_texts, list) or not subtitle_texts:
        raise ValueError("字幕文本列表不能为空")

    if not isinstance(audio_paths, list) or not audio_paths:
        raise ValueError("音频路径列表不能为空")

    if not isinstance(media_paths, list) or not media_paths:
        raise ValueError("媒体路径列表不能为空")

    # 校验输入参数长度一致性
    if len(subtitle_texts) != len(audio_paths) or len(audio_paths) != len(media_paths):
        raise ValueError("字幕文本列表、音频路径列表、媒体路径列表长度必须一致")

    # 检查草稿文件夹路径
    if not os.path.exists(draft_folder_path):
        raise FileNotFoundError(f"剪映草稿文件夹路径不存在: {draft_folder_path}")

    # 检查所有文件是否存在
    missing_files = []
    for media_path in media_paths:
        if not os.path.exists(media_path):
            missing_files.append(f"媒体文件: {media_path}")
    for audio_path in audio_paths:
        if not os.path.exists(audio_path):
            missing_files.append(f"音频: {audio_path}")
    if background_image and not os.path.exists(background_image):
        missing_files.append(f"背景图片: {background_image}")
    if background_music and not os.path.exists(background_music):
        missing_files.append(f"背景音乐: {background_music}")

    if missing_files:
        raise FileNotFoundError(f"以下文件不存在:\n" + "\n".join(missing_files))

    try:
        # 初始化草稿文件夹
        draft_folder = draft.DraftFolder(draft_folder_path)

        # 检查草稿是否已存在
        if draft_folder.has_draft(draft_name):
            raise FileExistsError(f"草稿 '{draft_name}' 已存在，不允许覆盖")

        # 判断媒体类型（图片/视频）并确定草稿尺寸
        all_images = True
        first_video_path = None

        # 检查是否有视频文件
        for path in media_paths:
            if path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                all_images = False
                first_video_path = path
                break

        # 获取尺寸信息
        if all_images:
            # 全是图片，使用第一张图片的尺寸
            try:
                with Image.open(media_paths[0]) as img:
                    width, height = img.size
            except Exception as e:
                raise RuntimeError(f"获取第一张图片尺寸失败: {str(e)}")
        else:
            # 至少有一个视频，使用第一个视频的尺寸
            first_video = draft.VideoMaterial(first_video_path)
            width, height = first_video.width, first_video.height

        # 根据横竖屏设置字幕参数
        if width > height:
            # 横屏
            font_size = 6.0
            subtitle_y = -0.8
        else:
            # 竖屏
            font_size = 13.0
            subtitle_y = -0.3

        # 创建新草稿
        script = draft_folder.create_draft(
            draft_name,
            width,
            height,
            allow_replace=False
        )

        # 添加所需轨道
        track_builder = script.add_track(TrackType.video, "媒体轨道") \
                             .add_track(TrackType.audio, "音频轨道") \
                             .add_track(TrackType.text, "字幕轨道")
        if background_image:
            track_builder.add_track(TrackType.video, "背景图片轨道", relative_index=3)
        if background_music:
            track_builder.add_track(TrackType.audio, "背景音乐轨道")

        current_time = 0
        total_duration = 0
        separators = r'([，。！,!?；])'

        # 处理每个片段（媒体、音频、字幕）
        for i in range(len(subtitle_texts)):
            audio_path = audio_paths[i]
            media_path = media_paths[i]
            subtitle_text = subtitle_texts[i]

            # 创建音频片段并获取时长
            audio_material = draft.AudioMaterial(audio_path)
            audio_duration = audio_material.duration
            time_range = trange(current_time, audio_duration)

            audio_segment = draft.AudioSegment(
                audio_path,
                time_range
            )
            script.add_segment(audio_segment, "音频轨道")

            # 判断媒体类型并创建相应片段
            is_image = media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))

            if is_image:
                # 处理图片片段
                media_segment = draft.VideoSegment(
                    media_path,
                    time_range
                )
                add_movement = add_image_movement
            else:
                # 处理视频片段
                video_material = draft.VideoMaterial(media_path)
                video_duration = video_material.duration

                # 根据裁剪设置决定处理方式
                if crop_video and audio_duration < video_duration:
                    # 裁剪模式：音频短于视频时，裁剪视频到音频长度
                    if mute_original_video:
                        media_segment = draft.VideoSegment(
                            media_path,
                            time_range,
                            source_timerange=trange(0, audio_duration),  # 裁剪视频源时间范围
                            volume=0.0  # 静音处理
                        )
                    else:
                        media_segment = draft.VideoSegment(
                            media_path,
                            time_range,
                            source_timerange=trange(0, audio_duration)  # 裁剪视频源时间范围
                        )
                else:
                    # 变速模式：音频长于视频时，或未开启裁剪时，调整视频速度
                    speed = video_duration / audio_duration
                    if mute_original_video:
                        media_segment = draft.VideoSegment(
                            media_path,
                            time_range,
                            speed=speed,
                            volume=0.0  # 静音处理
                        )
                    else:
                        media_segment = draft.VideoSegment(
                            media_path,
                            time_range,
                            speed=speed
                        )

                add_movement = add_video_movement

            # 设置媒体居中显示
            media_segment.clip_settings = ClipSettings(
                transform_x=0,
                transform_y=0,
            )

            # 添加关键帧确保保持比例
            media_segment.add_keyframe(
                KeyframeProperty.uniform_scale,
                time_offset=0,
                value=1.0
            )

            # 随机添加运镜效果
            if add_movement:
                effect = random.choice(camera_effects)
                effect(media_segment, audio_duration)

            script.add_segment(media_segment, "媒体轨道")

            # 处理字幕：根据参数决定是否拆分
            if split_subtitles:
                # 拆分字幕为短句并添加
                sentences = _split_subtitle(subtitle_text)
                total_length = len(subtitle_text)

                # 如果没有拆分出短句（无标点符号），使用原字幕
                if not sentences:
                    sentences = [subtitle_text]

                # 计算每个短句的显示时间并添加
                current_sub_time = current_time
                for sentence in sentences:
                    # 计算短句长度占比（避免除零错误）
                    if total_length == 0:
                        ratio = 1.0 / len(sentences)
                    else:
                        ratio = len(sentence) / total_length

                    # 计算当前短句的显示时长
                    sentence_duration = int(audio_duration * ratio)
                    # 确保至少有100ms的显示时间
                    sentence_duration = max(sentence_duration, 100000)

                    # 计算当前短句的时间范围
                    sentence_time_range = trange(current_sub_time, sentence_duration)

                    # 添加字幕片段
                    text_segment = draft.TextSegment(
                        re.sub(separators, '', sentence),
                        sentence_time_range,
                        font=draft.FontType.文轩体,
                        style=TextStyle(
                            color=(1.0, 1.0, 1.0),
                            size=font_size,
                            align=1,
                            auto_wrapping=True,
                            max_line_width=0.8,
                        ),
                        background=TextBackground(
                            color="#000000",
                            alpha=0.5,
                            round_radius=0.1,
                            height=0.15,
                            width=0.8
                        ),
                        clip_settings=ClipSettings(transform_y=subtitle_y)
                    )
                    script.add_segment(text_segment, "字幕轨道")

                    # 更新当前字幕时间
                    current_sub_time += sentence_duration
            else:
                # 不拆分，直接显示整段字幕
                text_segment = draft.TextSegment(
                    subtitle_text,
                    time_range,
                    font=draft.FontType.文轩体,
                    style=TextStyle(
                        color=(1.0, 1.0, 1.0),
                        size=font_size,
                        align=1,
                        auto_wrapping=True,
                        max_line_width=0.8,
                    ),
                    background=TextBackground(
                        color="#000000",
                        alpha=0.5,
                        round_radius=0.1,
                        height=0.15,
                        width=0.8
                    ),
                    clip_settings=ClipSettings(transform_y=subtitle_y)
                )
                script.add_segment(text_segment, "字幕轨道")

            # 更新时间
            current_time += audio_duration
            total_duration = current_time

        # 处理背景图片
        if background_image:
            image_segment = draft.VideoSegment(
                background_image,
                trange(0, total_duration)
            )
            script.add_segment(image_segment, "背景图片轨道")

        # 处理背景音乐
        if background_music:
            music_material = draft.AudioMaterial(background_music)
            music_duration = music_material.duration
            current_music_time = 0

            # 循环添加背景音乐直到达到总时长
            while current_music_time < total_duration:
                remaining_time = total_duration - current_music_time
                segment_duration = min(music_duration, remaining_time)

                music_segment = draft.AudioSegment(
                    background_music,
                    trange(current_music_time, segment_duration),
                    volume=0.3,
                    source_timerange=trange(0, segment_duration)
                )
                script.add_segment(music_segment, "背景音乐轨道")

                current_music_time += segment_duration

        # 保存草稿
        script.save()

        return f"剪映草稿 '{draft_name}' 创建成功！"

    except Exception as e:
        raise RuntimeError(f"创建剪映草稿失败: {str(e)}")
