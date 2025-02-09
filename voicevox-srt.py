"""voicevox-srt.py
Summary:
    VOICEVOXのvvprojファイルを、fugashiを用いた自然な改行を実現するSRT字幕ファイルに変換します。

    このスクリプトは、入力されたvvprojファイルから音声およびテキストデータを抽出し、
    以下の特徴を持つSRTファイルを生成します:
        - 日本語テキストはfugashiを使用して自然に分割されます。
        - 各字幕行は最大文字数（デフォルトは29文字）以内に制限されます。
        - 不自然な改行が発生した場合、非常に短い行をマージしてトークン単位で再分割し、可読性を向上させます。
    必要に応じて、メインブロック内のパラメータ（MAX_CHARS, VVPROJ_PATH, OUTPUT_SRT_PATH）を変更できます.

Usage:
    python voicevox-srt.py

License:
    This script is licensed under the terms provided by yKesamaru, the original author.
"""


import json

# GenericTaggerをインポート（柔軟な辞書形式に対応）
from fugashi import GenericTagger  # type: ignore

# GenericTaggerを使用してMeCabの設定ファイルとUTF-8版辞書を明示的に指定して初期化する
tagger = GenericTagger("-r /etc/mecabrc -d /var/lib/mecab/dic/ipadic-utf8")


def fugashi_segment_text(text):
    """
    fugashiを用いてテキストを文節に分割して返す関数。

    Args:
        text (str): 入力テキスト。

    Returns:
        list[str]: 分割された文節のリスト。
    """
    segments = []  # 分割結果を格納するリスト
    current_segment = ""  # 現在の文節を保持する文字列
    for word in tagger(text):
        current_segment += word.surface  # トークンの表層形を文節に追加
        if word.surface in ("。", "！", "？", "!", "?", "\n"):
            segments.append(current_segment.strip())  # 現在の文節をリストに追加
            current_segment = ""  # 文節をリセット
    if current_segment:
        segments.append(current_segment.strip())  # 残った文節を追加
    return segments


def calculate_audio_duration(query):
    """
    発話データから音声の総再生時間を計算して返す関数。

    Args:
        query (dict): 発話データの辞書。

    Returns:
        float: 発話の総再生時間（秒）。
    """
    if "accentPhrases" not in query:
        return 0.0
    total_duration = 0.0
    for phrase in query["accentPhrases"]:
        total_duration += sum(
            mora.get("vowelLength", 0.0) + mora.get("consonantLength", 0.0)
            for mora in phrase.get("moras", [])
        )
        total_duration += phrase.get("pauseMora", {}).get("vowelLength", 0.0)
    total_duration += query.get("prePhonemeLength", 0.1)
    total_duration += query.get("postPhonemeLength", 1.0)
    return round(total_duration, 6)


def format_srt_time(time_in_seconds):
    """
    秒単位の時間をSRT形式（hh:mm:ss,ms）に変換して返す関数。

    Args:
        time_in_seconds (float): 入力時間（秒）。

    Returns:
        str: SRT形式のタイムスタンプ文字列。
    """
    hours = int(time_in_seconds // 3600)
    minutes = int((time_in_seconds % 3600) // 60)
    seconds = int(time_in_seconds % 60)
    milliseconds = int(round((time_in_seconds - int(time_in_seconds)) * 1000))
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def split_long_segment(segment, max_chars):
    """
    長い文節を自然な切れ目（句読点等）で分割し、各行が最大文字数以内となるように短くして返す関数。

    Args:
        segment (str): 入力文節。
        max_chars (int): 1行あたりの最大文字数。

    Returns:
        list[str]: 分割された短い文節のリスト。
    """
    result = []
    remaining = segment
    punctuation_marks = "、。"
    while len(remaining) > max_chars:
        chunk = remaining[:max_chars]
        split_index = -1
        for i in range(len(chunk) - 1, -1, -1):
            if chunk[i] in punctuation_marks:
                split_index = i + 1
                break
        if split_index == -1 or split_index < max_chars * 0.5:
            split_index = max_chars
        result.append(remaining[:split_index].strip())
        remaining = remaining[split_index:]
    if remaining:
        result.append(remaining.strip())
    return result


def token_based_split(text, max_chars):
    """
    fugashiを用いてテキストを形態素（トークン）単位で分割し、トークンが途中で分断されないように連結して返す関数。

    Args:
        text (str): 入力テキスト。
        max_chars (int): 1行あたりの最大文字数。

    Returns:
        list[str]: 形態素境界で分割された行のリスト。
    """
    tokens = [token.surface for token in tagger(text)]
    lines = []
    current_line = ""
    for token in tokens:
        if len(current_line) + len(token) <= max_chars:
            current_line += token
        else:
            if current_line:
                lines.append(current_line)
            current_line = token
    if current_line:
        lines.append(current_line)
    return lines


def adjust_line_breaks(lines, max_chars=29, min_line_length=7):
    """
    分割済みの行リストを調整し、隣接する行で次の行の文字数が指定の閾値より短い場合、前後の行をマージして
    トークン単位で再分割し、自然な改行に整形して返す関数。

    Args:
        lines (list[str]): 元の行リスト。
        max_chars (int): 1行あたりの最大文字数。
        min_line_length (int): 自然な改行とみなす最小文字数。

    Returns:
        list[str]: 調整後の行リスト。
    """
    new_lines = []
    i = 0
    while i < len(lines):
        if i < len(lines) - 1 and len(lines[i + 1].strip()) < min_line_length:
            merged = lines[i].strip() + lines[i + 1].strip()
            splitted = token_based_split(merged, max_chars)
            new_lines.extend(splitted)
            i += 2
        else:
            new_lines.append(lines[i])
            i += 1
    return new_lines


def smart_split_text(text, max_chars=29):
    """
    日本語テキストを自然な文節に分割し、1行あたりの最大文字数以内に整形した文字列を返す関数。

    以下の手順で処理を行います:
      1. fugashiを用いてテキストを文節に分割する。
      2. 分割された文節をグリーディに連結し、各行がmax_charsを超えないようにする。
         なお、単一の文節がmax_charsを超える場合は、句読点等を利用してさらに分割します。
      3. 隣接する行で非常に短い行がある場合は、前後の行をマージし、形態素単位で再分割して自然な改行に整形します。

    Args:
        text (str): 入力テキスト。
        max_chars (int): 1行あたりの最大文字数。

    Returns:
        str: 改行を含む整形済みテキスト。
    """
    segments = fugashi_segment_text(text)
    lines = []
    current_line = ""
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) > max_chars:
            if current_line:
                lines.append(current_line)
                current_line = ""
            split_segments = split_long_segment(seg, max_chars)
            lines.extend(split_segments)
        else:
            if len(current_line) + len(seg) <= max_chars:
                current_line += seg
            else:
                if current_line:
                    lines.append(current_line)
                current_line = seg
    if current_line:
        lines.append(current_line)
    lines = adjust_line_breaks(lines, max_chars, min_line_length=7)
    return "\n".join(lines)


def convert_vvproj_to_srt(vvproj_file, output_srt, max_chars=29):
    """
    指定したvvprojファイルから音声およびテキストデータを抽出し、自然な文節分割と1行あたりの文字数制限を適用した上で、
    適切なタイムスタンプ付きのSRT字幕ファイルを生成して出力する関数。

    Args:
        vvproj_file (str): 入力vvprojファイルへのパス。
        output_srt (str): 出力するSRTファイルへのパス。
        max_chars (int): 各字幕行の最大文字数。

    Returns:
        None
    """
    with open(vvproj_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    talk_data = data.get("talk", {})
    audio_items = talk_data.get("audioItems", {})
    if not audio_items:
        print("audioItemsが見つかりません。JSONの構造を確認してください。")
        return
    srt_lines = []
    start_time = 0.0
    for idx, (key, item) in enumerate(audio_items.items()):
        text = item.get("text", "")
        text = smart_split_text(text, max_chars=max_chars)
        query = item.get("query", {})
        duration = calculate_audio_duration(query)
        if duration == 0.0:
            print(f"アイテム {key} のdurationが0です。")
        end_time = start_time + duration
        start_srt = format_srt_time(start_time)
        end_srt = format_srt_time(end_time)
        srt_lines.append(f"{idx + 1}")
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append(text)
        srt_lines.append("")
        start_time = end_time
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    print(f"SRTファイルを生成しました: {output_srt}")


if __name__ == "__main__":
    # 設定パラメータ（必要に応じて変更してください）
    MAX_CHARS = 30
    VVPROJ_PATH = "a.vvproj"
    OUTPUT_SRT_PATH = "output.srt"

    convert_vvproj_to_srt(VVPROJ_PATH, OUTPUT_SRT_PATH, max_chars=MAX_CHARS)
