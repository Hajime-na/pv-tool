from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


project_dir = Path(r"C:\Codex\PV\とげはてれかくし")
target = project_dir / "pv_lyrics_timing.json"
if target.exists():
    backup = project_dir / f"pv_lyrics_timing.before_16box_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup.write_bytes(target.read_bytes())

boxes = [
    ("Title", "title", 0.0, 13.0, []),
    ("Verse 1", "memory", 13.0, 25.351, ["ばらって なんだか", "ふしぎな花だね", "きれいって言うのに", "すこし こわいんだ"]),
    ("Verse 1 2", "memory", 25.351, 37.702, ["まっかな はなびら", "わらってるみたい", "でも ないてるよな", "ときも あるんだね"]),
    ("Pre-Chorus", "wind", 37.702, 62.403, ["みんなは きっと", "つよい花だと言う", "だけど ほんとは", "ちがうのかもね"]),
    ("Chorus", "bloom", 62.403, 74.754, ["とげは てれかくし", "ばらは さみしがり", "こわい花じゃなくて", "やさしい花かもね"]),
    ("Chorus 2", "bloom", 74.754, 87.105, ["つよそうに見えても", "ほんとは ちがうんだ", "だれにも言えない", "きもちがあるんだね"]),
    ("Verse 2", "memory", 87.105, 99.456, ["かぜが ふく日は", "すこし うれしそう", "あめの 日になると", "しずかに うつむく"]),
    ("Verse 2 2", "memory", 99.456, 111.806, ["さわると いたいし", "ほんとに いたいよ", "だけど その奥に", "なみだが あるみたい"]),
    ("Pre-Chorus", "wind", 111.806, 136.507, ["きれいなものほど", "ひとりに見えるなら", "それって なんだか", "かなしいことだね"]),
    ("Chorus", "bloom", 136.507, 148.858, ["とげは てれかくし", "ばらは さみしがり", "こわい花じゃなくて", "やさしい花かもね"]),
    ("Chorus 2", "bloom", 148.858, 161.209, ["つよそうに見えても", "ほんとは ちがうんだ", "だれにも言えない", "きもちがあるんだね"]),
    ("Bridge", "night", 161.209, 173.56, ["ぼくも ときどき", "うまく わらえない", "へいきじゃないのに", "へいきな ふりする"]),
    ("Bridge 2", "night", 173.56, 185.91, ["だから わかるよ", "ばらの きもちが", "だまって 咲くのは", "がんばってるから"]),
    ("Final Chorus", "last", 185.91, 198.261, ["とげは てれかくし", "ばらは さみしがり", "こわい花じゃなくて", "やさしい花なんだね"]),
    ("Final Chorus 2", "last", 198.261, 210.611, ["つよそうに見えても", "ほんとは ちがうんだ", "だれにも言えない", "きもちを 抱いてるんだ"]),
    ("Outro / Spoken", "memory", 210.611, 235.313, ["ばらって なんだか", "大人みたいだね", "きれいで むずかしくて", "ほんとは やさしい"]),
]

data = {
    "version": 1,
    "audio": "",
    "timings": [
        {
            "index": index,
            "section": section,
            "mood": mood,
            "start": round(start, 3),
            "end": round(end, 3),
            "lines": lines,
        }
        for index, (section, mood, start, end, lines) in enumerate(boxes)
    ],
}

target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {target} with {len(boxes)} boxes")
