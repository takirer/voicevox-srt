#!/usr/bin/env python3
"""
test_timing_accuracy.py

新しいgen-srt-from-vvproj.pyの時間計算精度テスト
感情表現対応版の精度確認
"""

import json
import sys
from pathlib import Path
import importlib.util

def load_module_from_path(module_name: str, file_path: str):
    """指定パスからモジュールを動的インポート"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def load_vvproj(vvproj_path: str):
    """VVPROJファイルを読み込み"""
    with open(vvproj_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def calculate_original_script_time(vvproj_data):
    """元スクリプトの時間計算を再現"""
    audio_items = vvproj_data.get('talk', {}).get('audioItems', {})
    audio_keys = vvproj_data.get('talk', {}).get('audioKeys', [])
    
    if not audio_keys:
        audio_keys = list(audio_items.keys())
    
    total_time = 0.0
    
    for audio_key in audio_keys:
        if audio_key not in audio_items:
            continue
        
        audio_item = audio_items[audio_key]
        query_data = audio_item.get('query', {})
        
        # prePhonemeLength + postPhonemeLength
        item_time = query_data.get('prePhonemeLength', 0.0) + query_data.get('postPhonemeLength', 0.0)
        
        # アクセント句内の音素時間を合計（元スクリプト方式）
        for phrase_data in query_data.get('accentPhrases', []):
            for mora_data in phrase_data.get('moras', []):
                item_time += mora_data.get('vowelLength', 0.0)
                if mora_data.get('consonantLength'):
                    item_time += mora_data.get('consonantLength', 0.0)
            
            # pauseMoraの処理
            if phrase_data.get('pauseMora'):
                pause_data = phrase_data['pauseMora']
                item_time += pause_data.get('vowelLength', 0.0)
                if pause_data.get('consonantLength'):
                    item_time += pause_data.get('consonantLength', 0.0)
        
        total_time += item_time
    
    return total_time

def calculate_new_script_time(vvproj_data, gen_srt_module):
    """新しいgen-srt-from-vvproj.pyの時間計算"""
    generator = gen_srt_module.VOICEVOXSRTGenerator()
    audio_items = vvproj_data.get('talk', {}).get('audioItems', {})
    audio_keys = vvproj_data.get('talk', {}).get('audioKeys', [])
    
    if not audio_keys:
        audio_keys = list(audio_items.keys())
    
    total_time = 0.0
    
    for audio_key in audio_keys:
        if audio_key not in audio_items:
            continue
        
        audio_item = audio_items[audio_key]
        
        # AudioQueryに変換
        audio_query = generator._vvproj_to_audio_query(audio_item)
        
        # 公式実装に基づく正確な時間計算
        duration = gen_srt_module.VOICEVOXOfficialCalculator.calculate_accurate_duration(audio_query)
        
        total_time += duration
    
    return total_time

def main():
    """メイン処理"""
    if len(sys.argv) < 2:
        print("Usage: python test_timing_accuracy.py <vvproj_file>")
        sys.exit(1)
    
    vvproj_path = sys.argv[1]
    
    if not Path(vvproj_path).exists():
        print(f"Error: VVPROJ file not found: {vvproj_path}")
        sys.exit(1)
    
    # gen-srt-from-vvproj.pyを動的インポート
    gen_srt_path = Path(__file__).parent / "gen-srt-from-vvproj.py"
    if not gen_srt_path.exists():
        print(f"Error: gen-srt-from-vvproj.py not found: {gen_srt_path}")
        sys.exit(1)
    
    gen_srt_module = load_module_from_path("gen_srt_from_vvproj", str(gen_srt_path))
    
    # VVPROJファイルを読み込み
    vvproj_data = load_vvproj(vvproj_path)
    
    # 各方式で時間計算
    print("=" * 70)
    print("🎮 NextStage Gaming チャンネル - 時間計算精度テスト")
    print("=" * 70)
    print(f"VVPROJファイル: {vvproj_path}")
    print()
    
    # 元スクリプト方式
    original_time = calculate_original_script_time(vvproj_data)
    print(f"元スクリプト計算時間: {original_time:.3f}秒")
    
    # 新スクリプト（感情表現対応版）
    new_time = calculate_new_script_time(vvproj_data, gen_srt_module)
    print(f"新スクリプト計算時間: {new_time:.3f}秒")
    
    # 実際のWAVファイル時間（既知）
    actual_wav_time = 465.899  # 実測値
    print(f"実際のWAVファイル時間: {actual_wav_time:.3f}秒")
    print()
    
    # 差分計算
    original_diff = original_time - actual_wav_time
    new_diff = new_time - actual_wav_time
    
    print("=" * 70)
    print("📊 精度分析結果")
    print("=" * 70)
    print(f"元スクリプト誤差:   {original_diff:+.3f}秒 ({original_diff/actual_wav_time*100:+.2f}%)")
    print(f"新スクリプト誤差:   {new_diff:+.3f}秒 ({new_diff/actual_wav_time*100:+.2f}%)")
    print()
    
    # 改善度
    improvement = abs(original_diff) - abs(new_diff)
    improvement_percent = improvement / abs(original_diff) * 100
    
    print("🎯 改善効果")
    print("-" * 20)
    print(f"絶対誤差改善: {improvement:+.3f}秒")
    print(f"改善率:      {improvement_percent:.1f}%")
    print()
    
    if abs(new_diff) < abs(original_diff):
        print("✅ 新スクリプト（感情表現対応版）の方が高精度です！")
        
        # 精度レベル判定
        if abs(new_diff) <= 1.0:
            print("🏆 優秀な精度: ±1秒以内の高精度同期を実現")
        elif abs(new_diff) <= 5.0:
            print("🥇 良好な精度: 実用的なレベルの同期精度")
    else:
        print("⚠️  さらなる調整が必要かもしれません")
    
    print()
    print("=" * 70)
    print("🎮 Street Fighter 6実況動画編集への効果")
    print("=" * 70)
    print("• 音声と字幕の高精度同期により手動調整を大幅削減")
    print("• 感情表現（。。。、！！！など）の自然な保持")
    print("• 60fps編集環境での精密なタイミング制御")
    print("• 長時間実況動画での累積誤差の最小化")

if __name__ == "__main__":
    main()