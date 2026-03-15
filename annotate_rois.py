"""
Normal CCTV ROI Polygon Annotator (Debug-Friendly)

STYLE GOALS (easier debugging):
- Each major stage has its own try/except with clear [STAGE X] labels
- Prints key diagnostics (paths, frame shape, ROI counts)
- Small helper functions (isolated failures)
- Safe saving (always tries to save progress on exit)

METHODS USED (for documentation/report):
1) Interactive ROI annotation (human-in-the-loop)
2) Polygon-based ROI representation (multi-ROI per video)
3) Incremental ROI saving action (press N to commit ROI)
4) Defensive programming (stage-wise try/except + diagnostic prints)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any

import cv2
import sys

CURRENT_FILE = Path(__file__).resolve()
LOSTFOUND_BACKEND_DIR = CURRENT_FILE.parent
OUTPUT_CONFIG= LOSTFOUND_BACKEND_DIR / "config.json"


KEY_QUIT = ord("q")
KEY_RESET = ord("r")
KEY_SAVE_ROI = ord("n")

WINDOW_NAME = "Left click = add point | N = save ROI | R = reset current | Q = finish & save"

# =============================
# GLOBALS (OpenCV callback needs globals)
# =============================
current_points: List[Tuple[int, int]] = []
all_polygons: List[List[Dict[str, float]]] = []
frame = None
frame_copy = None

# =============================
# HELPERS (each with try/except)
# =============================
def log_instructions():
    print("\nInstructions:")
    print("• Left-click to add polygon points (unlimited points)")
    print("• N = Save this ROI and start new one")
    print("• R = Reset current polygon")
    print("• Q = Finish & Save all ROIs")
    print("--------------------------------------")


def safe_load_first_frame(video_path: Path):
    """Method: Interactive ROI annotation (frame extraction as UI background)"""
    try:
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        ret, frm = cap.read()
        cap.release()

        if not ret or frm is None:
            raise RuntimeError("Failed to read first frame (ret=False or frame=None).")

        print(f"[OK] Loaded first frame. shape={frm.shape}")
        return frm

    except Exception as e:
        print("[ERROR] safe_load_first_frame failed.")
        print("Reason:", repr(e))
        return None


def draw_polygon_points_and_edges(img, pts: List[Tuple[int, int]], color=(0, 255, 0), thickness=2):
    """Draw closed polygon from points list."""
    try:
        if len(pts) < 2:
            return
        for i in range(len(pts)):
            cv2.circle(img, pts[i], 5, color, -1)
            cv2.line(img, pts[i], pts[(i + 1) % len(pts)], color, thickness)
    except Exception as e:
        print("[WARN] draw_polygon_points_and_edges failed.")
        print("Reason:", repr(e))


def redraw_all_saved_polygons(base_frame):
    """Method: Defensive programming (consistent UI redraw for debugging)."""
    try:
        img = base_frame.copy()
        for poly in all_polygons:
            pts = [(int(p["x"]), int(p["y"])) for p in poly]
            draw_polygon_points_and_edges(img, pts, color=(0, 255, 0), thickness=2)
        return img
    except Exception as e:
        print("[WARN] redraw_all_saved_polygons failed.")
        print("Reason:", repr(e))
        return base_frame.copy()


def save_config(polygons: List[List[Dict[str, float]]], output_path: Path) -> bool:
    """Method: Safe saving (persist ROIs to JSON)."""
    try:
        config: Dict[str, Any] = {"bounding_polygons": polygons}
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"[OK] Saved {len(polygons)} ROIs to {output_path.resolve()}")
        return True
    except Exception as e:
        print("[ERROR] Failed to save config.")
        print("Reason:", repr(e))
        return False


# =============================
# MOUSE CALLBACK (try/except)
# =============================
def mouse_callback(event, x, y, flags, param):
    """
    Method: Interactive ROI annotation
    - Left click: add point
    - Draw current poly in red (not committed yet)
    """
    global current_points, frame_copy

    try:
        if event == cv2.EVENT_LBUTTONDOWN:
            current_points.append((x, y))
            print(f"[ADD] point ({x},{y}) | current_points={len(current_points)}")

            # draw point + line on current working image
            cv2.circle(frame_copy, (x, y), 5, (0, 0, 255), -1)
            if len(current_points) > 1:
                cv2.line(frame_copy, current_points[-2], current_points[-1], (0, 0, 255), 2)

    except Exception as e:
        print("[ERROR] mouse_callback failed.")
        print("Reason:", repr(e))


# =============================
# MAIN
# =============================
def main():
    global frame, frame_copy, current_points, all_polygons

    # -------- STAGE 1: Read user input (AUTO via argv, fallback to input) --------
    try:
        # ✅ Priority 1: get path from command-line argument
        if len(sys.argv) >= 2:
            raw = sys.argv[1]
            print("[INFO] Got video path from argv.")
        else:
            # ✅ Priority 2: manual input (still works if run standalone)
            raw = input("Enter normal CCTV video path: ").strip()

        raw = raw.strip().strip('"').strip("'")
        if not raw:
            raise ValueError("Empty video path.")

        video_path = Path(raw)
        print(f"[INFO] Video path: {video_path.resolve() if video_path.exists() else video_path}")

    except Exception as e:
        print("[FATAL] STAGE 1 failed (input path).")
        print("Reason:", repr(e))
        return

    # -------- STAGE 2: Load first frame --------
    try:
        frame = safe_load_first_frame(video_path)
        if frame is None:
            raise RuntimeError("Frame is None (failed to load).")
        frame_copy = frame.copy()
    except Exception as e:
        print("[FATAL] STAGE 2 failed (load frame).")
        print("Reason:", repr(e))
        return

    # -------- STAGE 3: Setup window + callback --------
    try:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, 1280, 720)
        cv2.setMouseCallback(WINDOW_NAME, mouse_callback)
        log_instructions()
    except Exception as e:
        print("[FATAL] STAGE 3 failed (OpenCV window/callback).")
        print("Reason:", repr(e))
        return

    # -------- STAGE 4: UI Loop --------
    try:
        while True:
            cv2.imshow(WINDOW_NAME, frame_copy)
            key = cv2.waitKey(20) & 0xFF

            if key == KEY_QUIT:
                print("[INFO] Finish & Save.")
                break

            elif key == KEY_RESET:
                print("[INFO] Current ROI reset.")
                current_points = []
                # Reset to clean frame + redraw saved polygons
                frame_copy = redraw_all_saved_polygons(frame)

            elif key == KEY_SAVE_ROI:
                if len(current_points) < 3:
                    print("[WARN] Need at least 3 points to form polygon.")
                    continue

                # Convert current_points -> JSON-friendly polygon
                polygon = [{"x": float(x), "y": float(y)} for (x, y) in current_points]
                all_polygons.append(polygon)
                print(f"[INFO] Saved ROI #{len(all_polygons)} | points={len(current_points)}")

                # Draw committed polygon in green (permanent)
                pts_int = [(int(x), int(y)) for (x, y) in current_points]
                draw_polygon_points_and_edges(frame_copy, pts_int, color=(0, 255, 0), thickness=2)

                # Clear current points for next ROI
                current_points = []

    except Exception as e:
        print("[ERROR] STAGE 4 failed (UI loop crashed).")
        print("Reason:", repr(e))

    # -------- STAGE 5: Cleanup window --------
    try:
        cv2.destroyAllWindows()
    except Exception as e:
        print("[WARN] STAGE 5 (destroyAllWindows) failed.")
        print("Reason:", repr(e))

    # -------- STAGE 6: Save config --------
    try:
        save_config(all_polygons, OUTPUT_CONFIG)
        print(f"[INFO] Output path: {os.path.abspath(str(OUTPUT_CONFIG))}")
    except Exception as e:
        print("[ERROR] STAGE 6 failed (save config).")
        print("Reason:", repr(e))


if __name__ == "__main__":
    main()
