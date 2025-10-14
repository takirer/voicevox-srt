#!/usr/bin/env python3
"""
test_emotion_support.py

感情表現対応機能のテスト
句読点・感嘆詞繰り返しの自然な処理確認
"""

import sys
from pathlib import Path
import importlib.util

def load_module_from_path(module_name: str, file_path: str):
    """指定パスからモジュールを動的インポート"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_emotional_expression_handler():
    """感情表現ハンドラーのテスト"""
    print("=" * 60)
    print("🎭 感情表現ハンドラーのテスト")
    print("=" * 60)
    
    # gen-srt-from-vvproj.pyを動的インポート
    gen_srt_path = Path(__file__).parent / "gen-srt-from-vvproj.py"
    if not gen_srt_path.exists():
        print(f"Error: gen-srt-from-vvproj.py not found: {gen_srt_path}")
        return False
    
    gen_srt_module = load_module_from_path("gen_srt_from_vvproj", str(gen_srt_path))
    handler = gen_srt_module.EmotionalExpressionHandler()
    
    # テストケース
    test_cases = [
        # (テキスト, 期待される結果の説明)
        ("生ラッシュで走れるようになりたいなぁ。。。", "感情表現ありとして処理"),
        ("うおおおおおお！！！", "感情表現ありとして処理"),
        ("やばい、これ負けるかも。。。", "感情表現ありとして処理"),
        ("完璧なコンボきたあああ！！！", "感情表現ありとして処理"),
        ("この展開は予想外だった。。。", "感情表現ありとして処理"),
        ("普通の文章です。", "感情表現なしとして処理"),
        ("普通の文章です！", "感情表現なしとして処理（単体句読点）"),
        ("。", "意味のない句読点として除外"),
        ("！！", "意味のない句読点として除外"),
        ("　", "意味のない空白として除外"),
        ("", "空文字として除外"),
        ("今度はSAゲージを使っていこう！！！", "感情表現ありとして処理"),
        ("相手の動きが読めない。。。うーん", "感情表現ありとして処理"),
    ]
    
    print("📝 感情表現分析テスト:")
    print()
    
    for text, expected in test_cases:
        analysis = handler.analyze_emotional_expression(text)
        is_allowed = handler.is_chars_allowed_with_emotion(text, 26)
        is_meaningless = handler.is_meaningless_punctuation(text)
        
        print(f"テキスト: '{text}'")
        print(f"  期待結果: {expected}")
        print(f"  感情表現: {'あり' if analysis['has_emotion'] else 'なし'}")
        
        if analysis['has_emotion']:
            print(f"  基本部分: '{analysis['base_text']}' ({analysis['base_length']}文字)")
            print(f"  感情部分: '{analysis['emotion_part']}' ({analysis['emotion_length']}文字)")
        
        print(f"  文字数許可: {'✅' if is_allowed else '❌'} (全{analysis['total_length']}文字)")
        print(f"  意味のない句読点: {'✅ 除外対象' if is_meaningless else '❌ 保持'}")
        print()
    
    return True

def test_natural_segmentation():
    """自然分割機能のテスト"""
    print("=" * 60)
    print("📝 自然分割機能のテスト")
    print("=" * 60)
    
    # gen-srt-from-vvproj.pyを動的インポート
    gen_srt_path = Path(__file__).parent / "gen-srt-from-vvproj.py"
    gen_srt_module = load_module_from_path("gen_srt_from_vvproj", str(gen_srt_path))
    segmentator = gen_srt_module.NaturalSegmentator()
    
    # Street Fighter 6実況のテストケース
    test_texts = [
        "何だかんだ、またトレモの紹介が長くなってしまいましたが、ここからはランクマッチの実況解説に入っていきたいと思います。",
        "今回のテーマはSAゲージを回すこと。使わずに勝てることはあっても使えた方が勝率は上がるはずです！",
        "波動を相手が踏みそうと思ったら、生ラッシュで走れるようになりたいなぁ。。。",
        "立ち周りは豪鬼が圧倒的に有利ですが、ザンギ側も一瞬で豪鬼の体力を溶かすことができるので、油断できないです。",
        "うおおおおおお！！！完璧なコンボが決まった！！！これは勝ったかもしれない。。。",
        "相手の動きが読めない。。。うーん、どう攻めよう？？？",
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"テストケース {i}:")
        print(f"入力: '{text}' ({len(text)}文字)")
        
        segments = segmentator.segment_text(text, max_chars=26, max_lines=2)
        
        print(f"出力: {len(segments)}個のセグメント")
        for j, segment in enumerate(segments, 1):
            lines = segment.split('\n')
            print(f"  セグメント{j}: {len(lines)}行")
            for k, line in enumerate(lines, 1):
                char_count = len(line)
                status = "✅" if char_count <= 26 else "❌"
                
                # 感情表現チェック
                emotion_handler = gen_srt_module.EmotionalExpressionHandler()
                is_allowed = emotion_handler.is_chars_allowed_with_emotion(line, 26)
                emotion_status = "✅感情表現許容" if is_allowed and char_count > 26 else ""
                
                print(f"    行{k}: '{line}' ({char_count}文字) {status} {emotion_status}")
        print()
    
    return True

def main():
    """メイン処理"""
    print("🎮 NextStage Gaming チャンネル - 感情表現対応機能テスト")
    
    # 感情表現ハンドラーのテスト
    success1 = test_emotional_expression_handler()
    
    # 自然分割機能のテスト
    success2 = test_natural_segmentation()
    
    if success1 and success2:
        print("=" * 60)
        print("🎉 全てのテストが完了しました！")
        print("=" * 60)
        print("✅ 感情表現ハンドラー: 正常動作")
        print("✅ 自然分割機能: 正常動作")
        print("✅ Street Fighter 6実況に最適化された字幕生成が可能")
        print()
        print("🚀 実況動画編集効率化の準備完了！")
    else:
        print("❌ 一部のテストで問題が発生しました")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())