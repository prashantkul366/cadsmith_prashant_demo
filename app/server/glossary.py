"""English parameter names, read in Japanese.

A generated script declares its parameters as Python identifiers, and they
have to stay that way: the code is English, the CadQuery documentation the
Coder is given is English, and a Japanese identifier would be a a variable
the Refiner has never seen in any example it was trained on. So the names
on the sliders were English too - `Pad diameter`, `Slit width` - in a
window that was otherwise entirely Japanese.

They are not sentences, though. A parameter name is a compound of a small
vocabulary: across every part this app has built, 199 distinct names are
made of 134 distinct words, and the top forty of those words account for
most of every name. Japanese builds compounds in the same modifier-first
order, so `pad_diameter` is パッド径 word for word, and a dictionary does
the job without a model call, without a round trip, and identically every
time - which matters for a label somebody is about to drag.

What it will not do is guess. A name with a word that is not in here reads
back in English rather than half-translated: `バーブdiameter` is worse
than `Barb diameter`, because it looks like a bug rather than like a word
nobody has got to yet.
"""

from __future__ import annotations

import re

#: Names that are terms in their own right rather than the sum of their
#: words. Checked before anything is split up.
_TERMS = {
    "outer_diameter": "外径",
    "od": "外径",
    "id": "内径",
    "outside_diameter": "外径",
    "inner_diameter": "内径",
    "inside_diameter": "内径",
    "across_flats": "二面幅",
    "o_ring": "Oリング",
    "set_screw": "止めねじ",
    "num_teeth": "歯数",
    "teeth": "歯数",
    "teeth_number": "歯数",
    "number_of_teeth": "歯数",
    "tooth_count": "歯数",
    "centre_bore": "中心穴",
    "center_bore": "中心穴",
    "wall_thickness": "肉厚",
    # 大径 and 小径 already carry the 径; as words they would
    # double it, so they are only ever read as whole terms.
    "major_diameter": "大径",
    "minor_diameter": "小径",
    "pressure_angle": "圧力角",
    "pitch_diameter": "ピッチ円直径",
    "pitch_circle_diameter": "ピッチ円直径",
    "bolt_circle_diameter": "ボルト円直径",
    "saw_slot": "のこ溝",
    "xlen": "X方向長さ",
    "ylen": "Y方向長さ",
    "zlen": "Z方向長さ",
}

#: One word at a time, in the order they are written.
_WORDS = {
    # what a number measures
    "diameter": "直径", "radius": "半径", "length": "長さ", "width": "幅",
    "height": "高さ", "thickness": "厚さ", "depth": "深さ", "angle": "角度",
    "angular": "角度", "pitch": "ピッチ", "distance": "距離",
    "position": "位置", "offset": "オフセット", "size": "サイズ",
    "count": "数", "num": "数", "number": "数", "span": "スパン",
    "clearance": "クリアランス", "creepage": "沿面距離", "module": "モジュール",
    "pressure": "圧力", "nominal": "呼び", "total": "全", "per": "当たり",
    "start": "開始", "rise": "立上り", "gap": "すきま",
    # features cut into a part
    "hole": "穴", "holes": "穴", "bore": "内径", "slot": "長穴",
    "slit": "スリット", "groove": "溝", "flute": "溝", "flutes": "溝",
    "pocket": "ポケット", "cutout": "切欠き", "counterbore": "ざぐり",
    "countersink": "皿ざぐり", "chamfer": "面取り", "fillet": "フィレット",
    "recess": "凹み", "relief": "逃げ", "keyway": "キー溝", "thread": "ねじ",
    "tapped": "タップ", "tapping": "タップ", "drill": "ドリル",
    "through": "貫通", "taper": "テーパ", "step": "段", "contour": "輪郭",
    # features added to a part
    "boss": "ボス", "rib": "リブ", "web": "ウェブ", "gusset": "ガセット",
    "flange": "フランジ", "lug": "ラグ", "tab": "タブ", "ear": "耳",
    "pad": "パッド", "pin": "ピン", "pins": "ピン", "hub": "ハブ",
    "shoulder": "段", "stem": "ステム", "shank": "シャンク",
    "collar": "カラー", "knuckle": "ナックル", "lobe": "ローブ",
    "finger": "フィンガー", "fin": "フィン", "vane": "羽根", "blade": "羽根",
    # shapes a part is made of
    "plate": "プレート", "block": "ブロック", "bar": "バー", "rod": "ロッド",
    "disk": "ディスク", "disc": "ディスク", "ring": "リング",
    "cube": "立方体", "cone": "円錐", "conical": "円錐", "circle": "円",
    "sphere": "球", "spherical": "球面", "cylinder": "円筒",
    "strip": "ストリップ", "strap": "ストラップ", "panel": "パネル",
    "column": "柱", "body": "本体", "base": "ベース", "cap": "キャップ",
    "shaft": "軸", "socket": "ソケット", "seat": "座", "nose": "先端",
    "tip": "先端", "head": "頭部", "face": "面", "side": "側",
    "end": "端", "top": "上", "bottom": "下", "corner": "コーナー",
    "edge": "エッジ", "row": "列", "rows": "列",
    # named parts and hardware
    "screw": "ねじ", "bolt": "ボルト", "nut": "ナット", "washer": "ワッシャ",
    "dowel": "ダウエル", "bearing": "軸受", "seal": "シール",
    "roller": "ローラ", "clamp": "クランプ", "hinge": "ヒンジ",
    "fork": "フォーク", "handle": "ハンドル", "grip": "グリップ",
    "nozzle": "ノズル", "barb": "バーブ", "cable": "ケーブル",
    "bumper": "バンパー", "coin": "コイン", "key": "キー", "tie": "タイ",
    "saw": "のこ", "hex": "六角", "plain": "平", "sheet": "板",
    # what a feature is for
    "mounting": "取付", "locating": "位置決め", "lifting": "吊り",
    "safe": "安全", "nested": "ネスト", "radial": "半径方向",
    "outer": "外", "inner": "内", "centre": "中心", "center": "中心",
    "small": "小", "large": "大", "deg": "度",
    "x": "X", "y": "Y", "z": "Z",
    # measured off a live run rather than guessed at: these are the words
    # that turned up in names the first Japanese parts came back with.
    "spacing": "間隔", "overall": "全体", "tolerance": "公差",
    "opening": "開口", "inlet": "入口", "outlet": "出口", "port": "ポート",
    "channel": "流路", "wall": "肉", "flat": "平", "arc": "円弧",
    "apex": "頂点", "rim": "リム", "neck": "ネック", "shell": "シェル",
    "leg": "脚", "arm": "アーム", "bracket": "ブラケット", "mount": "取付",
    "spring": "ばね", "coil": "コイル", "helix": "らせん", "lead": "リード",
    "origin": "原点", "axis": "軸", "plane": "平面", "surface": "表面",
    "area": "面積", "volume": "体積", "mass": "質量", "density": "密度",
    "crest": "山", "root": "谷",
    "barrel": "バレル", "palm": "パーム", "stud": "スタッド",
    "square": "正方形", "round": "丸",
}

#: After another word, a diameter is written 径 rather than 直径: a hole's
#: is 穴径, not 穴直径. On its own it keeps the full spelling.
_IN_COMPOUND = {"diameter": "径"}


#: A thread designation is written the same in both languages: M8, M12x1.25.
_THREAD = re.compile(r"m\d{1,2}(?:x[\d.]+)?", re.IGNORECASE)


def english(name: str) -> str:
    """``hole_diameter`` -> ``Hole diameter``."""
    words = name.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else name


def _japanese(name: str) -> str:
    """``pad_diameter`` -> ``パッド径``, or "" if a word is not known.

    Longest match first, so a term made of several words is read as the
    term: `set_screw_counterbore_depth` is 止めねじ then ざぐり then 深さ,
    and not three words that happen to start with "set".
    """
    words = [w for w in name.split("_") if w]
    out: list[str] = []
    i = 0
    while i < len(words):
        for end in range(len(words), i, -1):
            term = _TERMS.get("_".join(words[i:end]))
            if term:
                out.append(term)
                i = end
                break
        else:
            word = words[i]
            if word.isdigit():
                out.append(word)                # the 12 of pad_12
            elif _THREAD.fullmatch(word):
                out.append(word.upper())        # m8 -> M8, which is written so
            else:
                # After another word, a diameter is written 径 rather than
                # 直径: a hole's is 穴径, not 穴直径.
                reading = (_IN_COMPOUND.get(word) if out else None) \
                    or _WORDS.get(word)
                if not reading:
                    return ""       # half-translated reads as a bug
                out.append(reading)
            i += 1
    return "".join(out)



def label(name: str, lang: str = "en") -> str:
    """What to write on the control for this parameter.

    Japanese when every word of the name is known, and the English name
    otherwise - never a mixture, which looks like a fault rather than like
    a gap in a dictionary.
    """
    if lang == "ja":
        reading = _japanese(name)
        if reading:
            return reading
    return english(name)


def coverage(names) -> tuple[list[str], list[str]]:
    """``(names read in Japanese, names that fall back to English)``."""
    known, unknown = [], []
    for name in names:
        (known if _japanese(name) else unknown).append(name)
    return known, unknown


def labels(names, langs=("en", "ja")) -> dict:
    """``{lang: {name: label}}`` for a set of parameter names.

    Both languages at once, and carried with the plan rather than resolved
    when it is drawn, because the browser has no dictionary and the panel
    has to relabel itself the moment somebody moves the language switch.
    """
    return {lang: {name: label(name, lang) for name in names}
            for lang in langs}
