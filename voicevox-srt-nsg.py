"""voicevox-srt-perfect-corrected.py
Summary:
    VOICEVOXのvvprojファイルを、音素レベルの正確な時間計算を用いたSRT字幕ファイルに変換します。
    
    修正された時間計算:
    - 開始時間: 音素レベルの正確な計算（既に正確）
    - 終了時間: n番目の終了時間 = n+1番目の開始時間（音声の連続性を保持）
    - 最後の字幕: 全体の長さと一致

Usage:
    python voicevox-srt-perfect-corrected.py

License:
    This script is licensed under the terms provided by yKesamaru, the original author.
    Modified by NextStage Gaming for perfect timing calculation.
"""

import json

try:
    from fugashi import GenericTagger
    tagger = GenericTagger("-r /opt/homebrew/etc/mecabrc -d /opt/homebrew/lib/mecab/dic/ipadic")
except ImportError:
    print("[WARNING] fugashi not available, using simple tokenization")
    tagger = None


def is_ascii_letter(ch):
    """指定された文字が英字（ASCII）であるかを判定して返す関数。"""
    return ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')


def fugashi_segment_text(text):
    """fugashiを用いてテキストを文節に分割して返す関数。"""
    if tagger is None:
        segments = []
        current_segment = ""
        for char in text:
            current_segment += char
            if char in ("。", "！", "？", "!", "?", "\n"):
                segments.append(current_segment.strip())
                current_segment = ""
        if current_segment.strip():
            segments.append(current_segment.strip())
        return segments
    
    segments = []
    current_segment = ""
    for word in tagger(text):
        current_segment += word.surface
        if word.surface in ("。", "！", "？", "!", "?", "\n"):
            segments.append(current_segment.strip())
            current_segment = ""
    if current_segment:
        segments.append(current_segment.strip())
    return segments


def calculate_audio_duration(query):
    """
    発話データから音声の総再生時間を計算して返す関数。
    オリジナルと完全に同一のロジック。
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


def build_mora_list_with_text_mapping(text, accent_phrases):
    """
    テキストと音素（moras）の対応関係を順序を保持して構築する関数。
    """
    mora_list = []
    text_to_mora_indices = {}
    text_pos = 0
    
    for phrase in accent_phrases:
        moras = phrase.get("moras", [])
        
        for mora in moras:
            mora_text = mora.get("text", "")
            vowel_length = mora.get("vowelLength", 0.0)
            consonant_length = mora.get("consonantLength", 0.0)
            
            mora_info = {
                'text': mora_text,
                'vowel_length': vowel_length,
                'consonant_length': consonant_length,
                'duration': vowel_length + consonant_length,
                'original_text_pos': text_pos if text_pos < len(text) else -1
            }
            mora_list.append(mora_info)
            
            # テキスト位置との対応を記録
            if text_pos < len(text):
                text_to_mora_indices[text_pos] = len(mora_list) - 1
                text_pos += 1
        
        # pauseMora の処理
        pause_mora = phrase.get("pauseMora")
        if pause_mora:
            pause_duration = pause_mora.get("vowelLength", 0.0)
            mora_info = {
                'text': '',
                'vowel_length': pause_duration,
                'consonant_length': 0.0,
                'duration': pause_duration,
                'original_text_pos': text_pos if text_pos < len(text) else -1,
                'is_pause': True
            }
            mora_list.append(mora_info)
            
            if text_pos < len(text) and text[text_pos] in "、。！？":
                text_to_mora_indices[text_pos] = len(mora_list) - 1
                text_pos += 1
    
    return mora_list, text_to_mora_indices


def calculate_chunk_precise_duration(chunk_text, original_text, mora_list, text_to_mora_indices):
    """
    分割されたチャンクテキストに対応する正確な読み上げ時間を計算する関数。
    """
    # チャンクテキストが元のテキストのどの位置にあるかを特定
    chunk_start_pos = original_text.find(chunk_text)
    if chunk_start_pos == -1:
        print(f"[WARNING] チャンクテキスト '{chunk_text}' が元のテキストで見つかりません")
        return 0.0, -1, -1
    
    chunk_end_pos = chunk_start_pos + len(chunk_text) - 1
    
    # 対応する音素のインデックス範囲を特定
    mora_start_idx = text_to_mora_indices.get(chunk_start_pos, -1)
    mora_end_idx = text_to_mora_indices.get(chunk_end_pos, -1)
    
    if mora_start_idx == -1 or mora_end_idx == -1:
        print(f"[WARNING] チャンク '{chunk_text}' に対応する音素が見つかりません")
        return 0.0, -1, -1
    
    # 対応する音素の時間を合計
    total_duration = 0.0
    for i in range(mora_start_idx, mora_end_idx + 1):
        if i < len(mora_list):
            total_duration += mora_list[i]['duration']
    
    return total_duration, mora_start_idx, mora_end_idx


def format_srt_time(time_in_seconds):
    """秒単位の時間をSRT形式（hh:mm:ss,ms）に変換して返す関数。"""
    hours = int(time_in_seconds // 3600)
    minutes = int((time_in_seconds % 3600) // 60)
    seconds = int(time_in_seconds % 60)
    milliseconds = int(round((time_in_seconds - int(time_in_seconds)) * 1000))
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def split_long_segment(segment, max_chars):
    """長い文節を自然な切れ目（句読点等）で分割する関数。"""
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
        segment_piece = remaining[:split_index].strip()
        remaining = remaining[split_index:]
        if remaining and remaining[0] in punctuation_marks:
            j = 0
            while j < len(remaining) and remaining[j] in punctuation_marks:
                j += 1
            segment_piece += remaining[:j]
            remaining = remaining[j:]
        result.append(segment_piece)
    if remaining:
        result.append(remaining.strip())
    return result


def token_based_split(text, max_chars):
    """fugashiを用いてテキストを形態素（トークン）単位で分割する関数。"""
    if tagger is None:
        tokens = text.split()
    else:
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


def adjust_line_breaks(lines, max_chars, min_line_length=7):
    """分割済みの行リストを調整し、自然な改行に整形する関数。"""
    new_lines = []
    i = 0
    while i < len(lines):
        merge_flag = False
        if i < len(lines) - 1:
            current_line = lines[i].rstrip()
            next_line = lines[i+1].lstrip()
            if current_line and next_line and is_ascii_letter(current_line[-1]) and is_ascii_letter(next_line[0]):
                merge_flag = True
            elif len(next_line) < min_line_length:
                merge_flag = True
        if merge_flag:
            merged = lines[i].strip() + lines[i+1].strip()
            splitted = token_based_split(merged, max_chars)
            new_lines.extend(splitted)
            i += 2
        else:
            new_lines.append(lines[i])
            i += 1
    return new_lines


def smart_split_text(text, max_chars):
    """日本語テキストを自然な文節に分割し、1行あたりの最大文字数以内に整形した行リストを返す関数。"""
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
    return lines


def split_lines_by_max_lines(lines, max_lines):
    """行リストをMAX_LINES制限に基づいて複数のチャンクに分割する関数。"""
    if max_lines <= 0:
        return [lines]
    
    if len(lines) <= max_lines:
        return [lines]
    
    chunks = []
    for i in range(0, len(lines), max_lines):
        chunk = lines[i:i + max_lines]
        chunks.append(chunk)
    
    return chunks


def convert_vvproj_to_srt_with_perfect_timing(vvproj_file, output_srt, max_chars, max_lines):
    """
    vvprojファイルから音素レベルの正確な時間計算を用いてSRT字幕ファイルを生成する関数。
    
    修正された時間計算:
    - 開始時間: 音素レベルの正確な計算（既に正確）
    - 終了時間: n番目の終了時間 = n+1番目の開始時間（音声の連続性を保持）
    - 最後の字幕: 全体の長さと一致
    """
    with open(vvproj_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # VVPROJ形式対応
    talk_data = data.get("talk", {})
    audio_keys = talk_data.get("audioKeys", [])
    audio_items = talk_data.get("audioItems", {})
    
    if not audio_keys or not audio_items:
        print("audioKeysまたはaudioItemsが見つかりません。")
        return
    
    # 第1パス: 全ての字幕アイテムの開始時間を計算
    all_subtitles = []  # (start_time, end_time_placeholder, lines)
    global_start_time = 0.0
    
    for audio_key in audio_keys:
        if audio_key not in audio_items:
            print(f"[WARNING] AudioKey {audio_key} not found in audioItems")
            continue
            
        item = audio_items[audio_key]
        text = item.get("text", "")
        
        if not text.strip():
            continue
        
        # 音素データの取得
        query = item.get("query", {})
        accent_phrases = query.get("accentPhrases", [])
        
        if not accent_phrases:
            print(f"[WARNING] アイテム {audio_key} にaccentPhrasesがありません。")
            continue
        
        # オリジナルと同一の方法で総時間を計算
        total_audio_duration = calculate_audio_duration(query)
        
        # テキストと音素の対応関係を構築
        mora_list, text_to_mora_indices = build_mora_list_with_text_mapping(text, accent_phrases)
        
        # テキストを行リストに変換
        lines = smart_split_text(text, max_chars=max_chars)
        
        # MAX_LINES制御: 行リストをチャンクに分割
        line_chunks = split_lines_by_max_lines(lines, max_lines)
        
        # prePhonemeLength と postPhonemeLength
        pre_phoneme_length = query.get("prePhonemeLength", 0.1)
        post_phoneme_length = query.get("postPhonemeLength", 1.0)
        
        # 各チャンクの開始時間を計算
        current_start = global_start_time
        
        for i, chunk_lines in enumerate(line_chunks):
            chunk_text = "".join(chunk_lines)  # チャンクのテキスト全体
            
            # 正確な読み上げ時間を計算
            chunk_duration, mora_start_idx, mora_end_idx = calculate_chunk_precise_duration(
                chunk_text, text, mora_list, text_to_mora_indices
            )
            
            # 最初のチャンクにはprePhonemeLength、最後のチャンクにはpostPhonemeLength を追加
            if i == 0:
                chunk_duration += pre_phoneme_length
            if i == len(line_chunks) - 1:
                chunk_duration += post_phoneme_length
            
            if chunk_duration == 0.0:
                print(f"[WARNING] チャンク '{chunk_text}' の時間計算ができませんでした。")
                continue
            
            # 字幕アイテムを追加（終了時間は後で修正）
            all_subtitles.append({
                'start_time': current_start,
                'end_time': current_start + chunk_duration,  # 仮の終了時間
                'lines': chunk_lines,
                'duration': chunk_duration
            })
            
            current_start += chunk_duration
        
        global_start_time += total_audio_duration
    
    # 第2パス: 終了時間を修正（n番目の終了時間 = n+1番目の開始時間）
    for i in range(len(all_subtitles)):
        if i < len(all_subtitles) - 1:
            # 次の字幕の開始時間を現在の字幕の終了時間にする
            all_subtitles[i]['end_time'] = all_subtitles[i + 1]['start_time']
        else:
            # 最後の字幕は全体の長さに合わせる
            all_subtitles[i]['end_time'] = global_start_time
    
    # 第3パス: SRTファイル生成
    srt_lines = []
    for i, subtitle in enumerate(all_subtitles):
        start_srt = format_srt_time(subtitle['start_time'])
        end_srt = format_srt_time(subtitle['end_time'])
        
        srt_lines.append(f"{i + 1}")
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append("\n".join(subtitle['lines']))
        srt_lines.append("")
    
    # SRTファイルに出力
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    
    print(f"完璧な時間計算によるSRTファイルを生成しました: {output_srt}")
    print(f"総SRTアイテム数: {len(all_subtitles)}")
    print(f"総時間: {global_start_time:.3f}秒")
    print(f"設定: MAX_CHARS={max_chars}, MAX_LINES={max_lines}")


if __name__ == "__main__":
    import sys
    import os
    
    # コマンドライン引数の処理
    if len(sys.argv) < 2:
        print("Usage: python voicevox-srt-perfect-corrected.py <vvproj_file> [max_chars] [max_lines]")
        print("  vvproj_file: VVPROJファイルのパス（絶対パスまたは相対パス）")
        print("  max_chars: 1行あたりの最大文字数（デフォルト: 30）")
        print("  max_lines: 1つの字幕の最大行数（デフォルト: 2、0以下で制限なし）")
        print("")
        print("例:")
        print("  python voicevox-srt-perfect-corrected.py sample.vvproj")
        print("  python voicevox-srt-perfect-corrected.py /path/to/file.vvproj 25 1")
        print("  python voicevox-srt-perfect-corrected.py ../data/voice.vvproj 40 0")
        sys.exit(1)
    
    # 引数の取得
    VVPROJ_PATH = sys.argv[1]
    MAX_CHARS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    MAX_LINES = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    
    # 入力ファイルの存在確認
    if not os.path.exists(VVPROJ_PATH):
        print(f"エラー: ファイルが見つかりません: {VVPROJ_PATH}")
        sys.exit(1)
    
    # 出力ファイルパスの生成（拡張子をvvproj→srtに変更）
    if VVPROJ_PATH.lower().endswith('.vvproj'):
        OUTPUT_SRT_PATH = VVPROJ_PATH[:-7] + '.srt'  # .vvproj (7文字) を .srt に置換
    elif VVPROJ_PATH.lower().endswith('.json'):
        OUTPUT_SRT_PATH = VVPROJ_PATH[:-5] + '.srt'  # .json (5文字) を .srt に置換
    else:
        OUTPUT_SRT_PATH = VVPROJ_PATH + '.srt'  # 拡張子を追加
    
    print(f"入力ファイル: {VVPROJ_PATH}")
    print(f"出力ファイル: {OUTPUT_SRT_PATH}")
    print(f"設定: MAX_CHARS={MAX_CHARS}, MAX_LINES={MAX_LINES}")
    print("")

    convert_vvproj_to_srt_with_perfect_timing(VVPROJ_PATH, OUTPUT_SRT_PATH, max_chars=MAX_CHARS, max_lines=MAX_LINES)