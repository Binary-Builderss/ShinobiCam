"""Regenerates the original bundled assets: assets/log.png and assets/icon.ico."""
from pathlib import Path

import cv2
from PIL import Image

from shinobicam.effect_engine import make_log_sprite

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    sprite = make_log_sprite(450)
    cv2.imwrite(str(ROOT / "assets" / "log.png"), sprite)
    rgba = Image.fromarray(cv2.cvtColor(make_log_sprite(256), cv2.COLOR_BGRA2RGBA))
    side = max(rgba.size)
    square = Image.new("RGBA", (side, side))
    square.paste(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
    square.save(ROOT / "assets" / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("assets aggiornati")
