"""Read Japanese edit instructions with the English vocabulary the app matches on.

server/edits.py recognises a parameter change by English word -
"thickness", "bore", "increase". A Japanese instruction carries exactly the
same information and matches none of it, so without this 「厚さを 5mm にする」
falls through to the Refiner: slow with a model backend configured, and
refused outright without one. A Japanese user could generate a part but not
change it.

Rather than teach every pattern in edits.py a second language, one pass
rewrites the instruction into the vocabulary those patterns already speak.
This is not a translation - the result is often not a sentence, and it is
never shown to anyone or sent to a model. Two consequences worth being clear
about:

* **Nothing here changes what the model is sent.** The rewrite is used to
  plan a parameter patch and then discarded; an instruction that falls
  through reaches the Refiner exactly as it was typed.
* **The refusals are the half that matters.** 「補強リブを追加する」 has to
  still come out as a rib, so the editor refuses to treat it as a parameter
  patch and hands it to the Refiner. If it did not, the patch path would land
  on whichever number happened to match and report a rib it never made. Ribs,
  fillets, chamfers, pockets, shells and the rest are in the table for that
  reason alone.

Word order is preserved, because the editor resolves an ambiguous request by
taking the number nearest the parameter it matched: the 5 in 「厚さを 5mm に
する」 has to stay beside the thickness.
"""

from __future__ import annotations

import re
import unicodedata

PARTICLES = "のをがはにでともやへ、。・「」（）：:"

_JAPANESE = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")

#: Built once: a label with its number after it (内径20mm) or before it
#: (20mm内径), for every entry in MEASURES and COUNTS.
_NUMBER = r"(\d+(?:\.\d+)?)"


def has_japanese(text: str) -> bool:
    """True when the text contains kana or kanji.

    Latin-only text is left completely alone, so an English request never
    passes through the rewrite and cannot be changed by it.
    """
    return bool(_JAPANESE.search(text or ""))


def spaced(text: str) -> str:
    """The same text with a space between kana/kanji and any Latin neighbour.

    Python's ``\\b`` treats kanji as word characters, so a designation written
    flush against one - 6203軸受, NEMA 17ステッピング - has no word boundary
    after it and every ``\\b``-anchored pattern in this package misses it.
    Padding the seam restores the boundary without altering a character.
    """
    padded = re.sub(r"(?<=[぀-ヿ㐀-䶿一-鿿])(?=[0-9A-Za-z])", " ", text or "")
    return re.sub(r"(?<=[0-9A-Za-z])(?=[぀-ヿ㐀-䶿一-鿿])", " ", padded)


#: What an edit instruction says, in the words ``server/edits.py`` matches on.
#: A different table from ``TERMS`` because the editor reads different things:
#: it wants the dimension noun (``thickness``), the direction (``increase``),
#: and above all the words that mean *new geometry* - a rib, a fillet, a
#: pocket - because those must be refused as parameter patches and handed to
#: the Refiner instead. Getting 「補強リブを追加する」 wrong in the other
#: direction would patch some unrelated number and call it a rib.
#:
#: Longest first: 肉厚 must win over 厚, and 面取り over 取り.
EDIT_TERMS = (
    # dimensions, in the canonical form edits._SYNONYMS already knows
    ("外径", "outer diameter"),
    ("内径", "inner diameter"),
    ("肉厚", "wall thickness"),
    ("壁厚", "wall thickness"),
    ("板厚", "thickness"),
    ("厚さ", "thickness"),
    ("厚み", "thickness"),
    ("直径", "diameter"),
    ("半径", "radius"),
    ("全長", "length"),
    ("長さ", "length"),
    ("高さ", "height"),
    ("深さ", "depth"),
    ("軸穴", "bore"),
    ("ボア", "bore"),
    ("穴数", "hole count"),
    ("個数", "count"),
    ("歯数", "teeth"),
    ("歯幅", "face width"),
    ("線径", "wire diameter"),
    ("自由長", "free length"),
    ("モジュール", "module"),
    ("ピッチ", "pitch"),
    ("角度", "angle"),
    ("公差", "tolerance"),
    ("間隔", "spacing"),
    ("フランジ", "flange"),
    ("ハブ", "hub"),
    ("幅", "width"),
    ("穴", "hole"),
    ("径", "diameter"),
    # new geometry: these have to survive into the English so the editor
    # refuses the patch and calls the Refiner
    ("補強リブ", "reinforcing rib"),
    ("リブ", "rib"),
    ("ガセット", "gusset"),
    ("面取り", "chamfer"),
    ("フィレット", "fillet"),
    ("角丸", "fillet"),
    ("ねじ山", "thread"),
    ("ローレット", "knurl"),
    ("テーパ", "taper"),
    ("スロット", "slot"),
    ("長穴", "slot"),
    ("ポケット", "pocket"),
    ("ボス", "boss"),
    ("シェル", "shell"),
    ("肉抜き", "shell"),
    ("ミラー", "mirror"),
    ("回転", "rotate"),
    ("押し出し", "extrude"),
    ("ロフト", "loft"),
    ("スイープ", "sweep"),
    # direction
    ("増やす", "increase"),
    ("増やして", "increase"),
    ("減らす", "reduce"),
    ("減らして", "reduce"),
    ("大きく", "larger"),
    ("小さく", "smaller"),
    ("太く", "widen"),
    ("細く", "thinner"),
    ("厚く", "thicken"),
    ("薄く", "thinner"),
    ("長く", "lengthen"),
    ("短く", "shorten"),
    ("高く", "taller"),
    ("低く", "shorter"),
    ("追加", "add"),
    ("足して", "add"),
    ("削除", "remove"),
    ("除去", "remove"),
    ("なくす", "remove"),
    ("移動", "move"),
    ("変更", "change"),
    ("にする", "set to"),
    ("してください", " "),
    ("します", " "),
    ("して", " "),
    ("する", " "),
    ("ミリ", "mm"),
    ("度", "degrees"),
)

#: Counter suffixes. 「6 個の穴」 counts holes; left in place the 個 would sit
#: between the number and the noun and push them apart, and the editor picks
#: the number nearest the parameter it matched.
COUNTERS = ("個", "本", "枚", "箇所", "つ", "カ所", "ヶ所")


def to_english_instruction(text: str) -> str:
    """An edit instruction in the vocabulary ``server/edits.py`` matches on.

    Word order is largely preserved, because the editor resolves an ambiguous
    request by taking the number nearest the parameter it matched: 「厚さを
    5mm にする」 has to come out with the 5 still beside the thickness.
    """
    out = unicodedata.normalize("NFKC", text or "")
    for japanese, english in EDIT_TERMS:
        out = out.replace(japanese, f" {english} ")
    for counter in COUNTERS:
        out = out.replace(counter, " ")
    out = "".join(" " if ch in PARTICLES else ch for ch in out)
    return " ".join(spaced(out).split())
