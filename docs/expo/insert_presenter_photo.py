"""Drop the presenter's headshot into the deck's presenter slide.

    python docs/expo/insert_presenter_photo.py my-headshot.jpg

The photo is centre-cropped to a square and placed in the dashed box on the
"Who you are talking to" slide; the placeholder box and its instructions go
away with it. The deck is written to a new file unless --in-place is given,
so a bad crop never costs you the original.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Inches

HERE = Path(__file__).resolve().parent
DECK = HERE / "CADSmith-Expo-Deck.pptx"
MARKER = "PRESENTER PHOTO"


def square(path: Path, out: Path, side: int = 1200) -> Path:
    """Centre-crop to a square, because the slot is square."""
    image = Image.open(path).convert("RGB")
    edge = min(image.size)
    left = (image.width - edge) // 2
    top = (image.height - edge) // 3          # faces sit above centre
    image = image.crop((left, top, left + edge, top + edge))
    image = image.resize((side, side), Image.LANCZOS)
    image.save(out, quality=95)
    return out


def drop(shape) -> None:
    shape._element.getparent().remove(shape._element)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", help="the headshot: JPEG or PNG")
    parser.add_argument("--deck", default=str(DECK))
    parser.add_argument("--out", default=None)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()

    deck = Path(args.deck)
    photo = Path(args.photo)
    if not photo.exists():
        print(f"no such photo: {photo}")
        return 1

    prs = Presentation(str(deck))
    for slide in prs.slides:
        label = next((s for s in slide.shapes
                      if s.has_text_frame and MARKER in s.text_frame.text), None)
        if label is None:
            continue

        # The dashed slot is the smallest empty shape the label sits inside -
        # the card behind it contains the label too, and must stay.
        holders = [s for s in slide.shapes
                   if s is not label
                   and not (s.has_text_frame and s.text_frame.text.strip())
                   and s.left <= label.left and s.top <= label.top
                   and s.left + s.width >= label.left + label.width
                   and s.top + s.height >= label.top + label.height]
        if not holders:
            print("found the label but not the box it sits in")
            return 1
        slot = min(holders, key=lambda s: s.width * s.height)

        cropped = square(photo, HERE / "presenter-photo.jpg")
        side = min(slot.width, slot.height)
        slide.shapes.add_picture(
            str(cropped),
            slot.left + (slot.width - side) // 2,
            slot.top + (slot.height - side) // 2,
            side, side)
        drop(label)
        drop(slot)

        out = Path(args.out) if args.out else (
            deck if args.in_place else deck.with_name(deck.stem + "-with-photo.pptx"))
        prs.save(str(out))
        print(f"wrote {out}")
        return 0

    print(f"no slide carries the text {MARKER!r} — is this the expo deck?")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
