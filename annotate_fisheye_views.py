import cv2
import json
import numpy as np
import sys
from pathlib import Path

from lostandfound import FisheyePreprocessor, FISHEYE_VIEW_CONFIGS

CURRENT_FILE = Path(__file__).resolve()
LOSTFOUND_BACKEND_DIR = CURRENT_FILE.parent
CONFIG_PATH = LOSTFOUND_BACKEND_DIR / "config.json"

KEY_NEXT = ord("n")
KEY_PREV = ord("p")
KEY_QUIT = ord("q")
KEY_CLEAR = ord("c")
KEY_UNDO = ord("u")   # undo last point / polygon

# Window size (smaller than full screen)
WIN_W = 1280
WIN_H = 720

drawing = False
current_poly = []
polygons = []


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


def get_video_path():
    """Accept video path from argv (preferred), fallback to input()."""
    if len(sys.argv) >= 2:
        raw = sys.argv[1]
        print("[INFO] Got video path from argv.")
    else:
        raw = input("Enter fisheye video path: ").strip()

    raw = raw.strip().strip('"').strip("'")
    if not raw:
        raise ValueError("Empty video path.")
    return raw


def mouse_draw(event, x, y, flags, param):
    global drawing, current_poly, polygons

    if event == cv2.EVENT_LBUTTONDOWN:
        current_poly.append((x, y))
        drawing = True
        print(f"[ADD] point ({x},{y})")

    elif event == cv2.EVENT_RBUTTONDOWN:
        # right click closes current polygon
        if len(current_poly) >= 3:
            polygons.append(current_poly.copy())
            print(f"[CLOSE] polygon with {len(current_poly)} points")
        else:
            print("[WARN] Need at least 3 points to close polygon")
        current_poly = []


def draw_hud(img):
    """
    Small tips panel that doesn't block the screen.
    Draw a semi-transparent box at top-left.
    """
    overlay = img.copy()
    x1, y1 = 10, 10
    x2, y2 = 520, 85  # small box
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), -1)
    alpha = 0.35
    img[:] = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

    tips1 = "LClick:add  RClick:close  U:undo  C:clear"
    tips2 = "N:next  P:prev  Q:quit"
    cv2.putText(img, tips1, (x1 + 10, y1 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, tips2, (x1 + 10, y1 + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def annotate_view(view_img, view_name, existing_polys=None):
    """
    Annotate one view.
    - Left click: add point
    - Right click: close polygon
    - U: undo last point / last polygon
    - C: clear all
    - N: next view
    - P: previous view
    - Q: quit
    """
    global drawing, current_poly, polygons
    drawing = False
    current_poly = []
    polygons = []

    if existing_polys:
        polygons = [poly.copy() for poly in existing_polys]

    clone = view_img.copy()

    # ✅ window setup (smaller)
    cv2.namedWindow(view_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(view_name, WIN_W, WIN_H)
    cv2.setMouseCallback(view_name, mouse_draw)

    while True:
        img = clone.copy()

        # draw saved polygons (green)
        for poly in polygons:
            pts = np.array(poly, dtype=np.int32)
            cv2.polylines(img, [pts], True, (0, 255, 0), 2)

        # draw current polygon (red, not closed)
        if len(current_poly) > 1:
            pts = np.array(current_poly, dtype=np.int32)
            cv2.polylines(img, [pts], False, (0, 0, 255), 2)

        # ✅ small HUD tips (non-blocking)
        img = draw_hud(img)

        cv2.imshow(view_name, img)
        key = cv2.waitKey(20) & 0xFF

        if key == KEY_CLEAR:
            polygons.clear()
            current_poly.clear()
            print("[CLEAR] cleared all polygons")

        elif key == KEY_UNDO:
            if current_poly:
                removed = current_poly.pop()
                print(f"[UNDO] removed point {removed}")
            elif polygons:
                polygons.pop()
                print("[UNDO] removed last polygon")
            else:
                print("[UNDO] nothing to undo")

        elif key == KEY_NEXT:
            cv2.destroyWindow(view_name)
            return polygons, "next"

        elif key == KEY_PREV:
            cv2.destroyWindow(view_name)
            return polygons, "prev"

        elif key == KEY_QUIT:
            cv2.destroyWindow(view_name)
            return polygons, "quit"


def to_config_polys(polys):
    return [[{"x": int(x), "y": int(y)} for (x, y) in poly] for poly in polys]


def from_config_polys(cfg_polys):
    out = []
    for poly in cfg_polys or []:
        out.append([(int(p["x"]), int(p["y"])) for p in poly])
    return out


def main():
    # ✅ accept passed video path
    try:
        video = get_video_path()
    except Exception as e:
        print("[FATAL] Invalid video path:", repr(e))
        return

    VIEW_NAMES = [cfg["name"] for cfg in FISHEYE_VIEW_CONFIGS]

    prep = FisheyePreprocessor(
        view_configs=FISHEYE_VIEW_CONFIGS,
        config_path="config.json"
    )

    if not prep.open(video):
        print("[ERROR] Failed to open fisheye video.")
        return

    ok, frame = prep.read_frame()
    if not ok or frame is None:
        print("[ERROR] Failed to read first frame.")
        return

    views = prep.get_views(frame)
    views_by_name = {v["name"]: v for v in views}

    cfg = load_config()
    cfg.setdefault("fisheye_polygons", {})

    idx = 0
    while 0 <= idx < len(VIEW_NAMES):
        view_name = VIEW_NAMES[idx]
        print(f"\n=== Annotating [{idx+1}/{len(VIEW_NAMES)}] {view_name} ===")

        selected = views_by_name.get(view_name)
        if selected is None:
            print(f"[WARN] {view_name} not found. Skipping.")
            idx += 1
            continue

        existing = from_config_polys(cfg["fisheye_polygons"].get(view_name, []))

        polys, action = annotate_view(selected["image"], view_name, existing_polys=existing)

        cfg["fisheye_polygons"][view_name] = to_config_polys(polys)
        save_config(cfg)
        print(f"[SAVE] Saved {len(polys)} polygon(s) for '{view_name}'")

        if action == "quit":
            print("[INFO] User quit early. Progress saved.")
            break
        elif action == "next":
            idx += 1
        elif action == "prev":
            idx = max(0, idx - 1)

    print("\n✅ Done. All polygons saved to config.json.")
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass


if __name__ == "__main__":
    main()
