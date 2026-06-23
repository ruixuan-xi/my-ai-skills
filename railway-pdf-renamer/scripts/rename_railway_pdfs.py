# -*- coding: utf-8 -*-
"""
铁路电子客票PDF批量重命名工具
从铁路电子客票PDF中提取日期、出发地、目的地、金额，按指定格式重命名。

用法:
    python rename_railway_pdfs.py <文件夹路径> [--dry-run] [--format <格式>]

参数:
    <文件夹路径>    包含PDF文件的文件夹路径
    --dry-run       仅预览重命名结果，不实际执行
    --format        自定义命名格式，默认: {date}-{from}-{to}-{amount}
                    可用变量: {date}, {from}, {to}, {amount}, {train}, {seat}

依赖:
    pip install pypdf

注意:
    部分铁路电子客票PDF因字体描述符同时包含/FontFile2和/FontFile3，
    会导致pypdf抛出"More than one /FontFile found"错误。
    本脚本已内置fallback方案：直接解析ContentStream并用GBK解码。
"""
import os
import re
import sys
import argparse

try:
    import pypdf
    from pypdf.generic import ContentStream, TextStringObject
except ImportError:
    print("ERROR: pypdf not installed. Run: pip install pypdf")
    sys.exit(1)


def extract_text_standard(pdf_path):
    """标准方式提取PDF文本（适用于大部分铁路电子客票）"""
    reader = pypdf.PdfReader(pdf_path, strict=False)
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text)
    return "\n".join(texts)


def extract_text_fallback(pdf_path):
    """Fallback方案：直接解析ContentStream，用GBK解码（解决字体描述符异常）"""
    reader = pypdf.PdfReader(pdf_path, strict=False)
    all_text = []
    for page in reader.pages:
        content = ContentStream(page["/Contents"], reader)
        for operands, operator in content.operations:
            if operator == b"Tj":
                for op in operands:
                    if isinstance(op, TextStringObject):
                        raw = op.original_bytes if hasattr(op, "original_bytes") else bytes(op, "latin-1")
                        try:
                            decoded = raw.decode("gbk")
                        except Exception:
                            decoded = str(op)
                        all_text.append(decoded)
            elif operator == b"TJ":
                for op_list in operands:
                    if isinstance(op_list, list):
                        for item in op_list:
                            if isinstance(item, TextStringObject):
                                raw = item.original_bytes if hasattr(item, "original_bytes") else bytes(item, "latin-1")
                                try:
                                    decoded = raw.decode("gbk")
                                except Exception:
                                    decoded = str(item)
                                all_text.append(decoded)
    return "".join(all_text)


def extract_text(pdf_path):
    """提取PDF文本，自动选择标准或fallback方案"""
    try:
        text = extract_text_standard(pdf_path)
        if text and len(text.strip()) > 10:
            return text
    except Exception:
        pass
    return extract_text_fallback(pdf_path)


def parse_ticket_info(text):
    """从PDF文本中解析日期、出发地、目的地、金额"""
    info = {}

    # 提取日期: 2026年05月11日 / 2026 年 05 月 11 日
    date_match = re.search(r"(\d{4})\s*年\s*(\d{2})\s*月\s*(\d{2})\s*日", text)
    if date_match:
        info["date"] = f"{date_match.group(1)}{date_match.group(2)}{date_match.group(3)}"
    else:
        info["date"] = "UNKNOWN_DATE"

    # 提取金额: 票价 : ￥ 242.00 / 票价:￥577.50
    amount_match = re.search(r"票价\s*[:：]\s*[￥¥]?\s*([\d.]+)", text)
    if amount_match:
        amount = float(amount_match.group(1))
        # 整数去掉小数点
        if amount == int(amount):
            info["amount"] = str(int(amount))
        else:
            info["amount"] = str(amount)
    else:
        info["amount"] = "UNKNOWN_AMOUNT"

    # 提取站名
    # 标准提取: 中文站名在车次之后，顺序为"到达站出发站"
    # Fallback提取: 中文站名在车次之前，顺序为"出发站到达站"
    stations = re.findall(r"([\u4e00-\u9fa5]+)\s*站", text)

    # 判断提取方式：检查"站"字是否出现在车次号之前
    train_match_pos = re.search(r"[GTDCZK]\d{1,5}", text)
    if train_match_pos and stations:
        first_station_pos = text.find("站")
        if first_station_pos < train_match_pos.start():
            # Fallback: 站名在车次之前，顺序为出发-到达
            info["from"] = stations[0]
            info["to"] = stations[1]
        else:
            # 标准: 站名在车次之后，顺序为到达-出发，需要交换
            if len(stations) >= 2:
                info["from"] = stations[-1]
                info["to"] = stations[-2]
            else:
                info["from"] = "UNKNOWN_FROM"
                info["to"] = "UNKNOWN_TO"
    elif len(stations) >= 2:
        # 无法判断，默认取最后两个
        info["from"] = stations[-2]
        info["to"] = stations[-1]
    else:
        # Fallback: 尝试从 "A站B站" 模式中提取
        station_pair = re.search(r"([\u4e00-\u9fa5]+)\s*站([\u4e00-\u9fa5]+)\s*站", text)
        if station_pair:
            info["from"] = station_pair.group(1)
            info["to"] = station_pair.group(2)
        else:
            info["from"] = "UNKNOWN_FROM"
            info["to"] = "UNKNOWN_TO"

    # 提取车次（可选）
    train_match = re.search(r"[GTDCZK]\d{1,5}", text)
    if train_match:
        info["train"] = train_match.group(0)
    else:
        info["train"] = ""

    return info


def build_filename(info, fmt="{date}-{from}-{to}-{amount}"):
    """根据信息和格式生成新文件名"""
    name = fmt.format(**info)
    # 清理文件名中的非法字符
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    return name + ".pdf"


def rename_pdfs(folder, fmt="{date}-{from}-{to}-{amount}", dry_run=False):
    """批量重命名文件夹中的铁路电子客票PDF"""
    pdf_files = sorted([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])

    if not pdf_files:
        print(f"未找到PDF文件: {folder}")
        return

    print(f"找到 {len(pdf_files)} 个PDF文件\n")

    renamed = 0
    skipped = 0
    errors = 0

    for fname in pdf_files:
        fpath = os.path.join(folder, fname)
        try:
            text = extract_text(fpath)
            info = parse_ticket_info(text)
            new_name = build_filename(info, fmt)
            new_path = os.path.join(folder, new_name)

            # 处理重名
            if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(fpath):
                base, ext = os.path.splitext(new_name)
                counter = 1
                while os.path.exists(os.path.join(folder, f"{base}_{counter}{ext}")):
                    counter += 1
                new_name = f"{base}_{counter}{ext}"
                new_path = os.path.join(folder, new_name)

            if dry_run:
                print(f"[DRY-RUN] {fname} -> {new_name}")
                print(f"          日期={info['date']} 出发={info['from']} 到达={info['to']} 金额={info['amount']}")
            else:
                os.rename(fpath, new_path)
                print(f"[OK] {fname} -> {new_name}")
            renamed += 1
        except Exception as e:
            print(f"[ERROR] {fname}: {e}")
            errors += 1

    print(f"\n=== 完成: {renamed} 重命名, {errors} 错误 ===")


def main():
    parser = argparse.ArgumentParser(description="铁路电子客票PDF批量重命名工具")
    parser.add_argument("folder", help="包含PDF文件的文件夹路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际重命名")
    parser.add_argument("--format", default="{date}-{from}-{to}-{amount}",
                        help="命名格式，可用变量: {date}, {from}, {to}, {amount}, {train}, {seat}")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"错误: 文件夹不存在: {args.folder}")
        sys.exit(1)

    rename_pdfs(args.folder, args.format, args.dry_run)


if __name__ == "__main__":
    main()
