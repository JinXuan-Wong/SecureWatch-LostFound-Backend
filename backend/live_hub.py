# backend/live_hub.py
import time
import threading
from typing import Dict, Any, List, Optional


class LiveHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._cams: Dict[str, Dict[str, Any]] = {}

    def get_state(self) -> Dict[str, Any]:
        """
        Safe snapshot for /api/live/state.
        MUST match frontend: { cameras: { cam_id: {updated_at, views, lost_items} } }
        """
        try:
            return {"cameras": self.snapshot()}
        except Exception:
            return {"cameras": {}}

    # ------------------------------------------------------------
    # ✅ Helper: normalize det list + ensure view_id global for fisheye
    # ------------------------------------------------------------
    def _normalize_dets(self, dets: Any, gi: int) -> List[Dict[str, Any]]:
        if dets is None:
            return []
        if not isinstance(dets, list):
            dets = [dets]

        out: List[Dict[str, Any]] = []
        for d in dets:
            if not isinstance(d, dict):
                continue

            dd = dict(d)

            # local view_id could be in view_id/view_idx/local_id
            local = dd.get("view_id", dd.get("view_idx", dd.get("local_id", 0)))
            try:
                local = int(local)
            except Exception:
                local = 0

            # ✅ GLOBAL mapping (Group A => 0..3, Group B => 4..7)
            # If not fisheye (gi=0 and locals may already be global), this is still safe.
            if gi == 0:
                global_id = local
            else:
                # if already global (4..7), keep it
                if 4 <= local <= 7:
                    global_id = local
                else:
                    global_id = 4 + (local % 4)

            dd["view_id"] = global_id

            # keep these if backend uses them later
            dd.setdefault("img_w", dd.get("img_w") or 640)
            dd.setdefault("img_h", dd.get("img_h") or 480)

            out.append(dd)

        return out

    def update(self, cam_id: str, views: List[Dict[str, Any]], lost_items: Optional[List[Any]] = None):
        """
        Store latest views and optional jpg bytes into hub.
        views can be:
          - NORMAL: 1 view ("Main")
          - FISHEYE: 2 views ("Group A", "Group B") each containing dets for local 0..3
        """
        now = time.time()
        if lost_items is None:
            lost_items = []

        clean_views = []

        for i, v in enumerate(views or []):
            if not isinstance(v, dict):
                continue

            name = v.get("name", f"View {i}")

            # detect group index:
            # prefer explicit gi/group_idx, else based on name/group, else enumerate
            gi = v.get("gi", v.get("group_idx", None))
            if gi is None:
                g = (v.get("group", "") or "").strip().upper()
                if g == "A":
                    gi = 0
                elif g == "B":
                    gi = 1
                else:
                    # infer from name
                    nm = str(name).lower()
                    if "group b" in nm:
                        gi = 1
                    elif "group a" in nm:
                        gi = 0
                    else:
                        gi = i  # fallback
            try:
                gi = int(gi)
            except Exception:
                gi = i

            # pull dets from either key
            raw_dets = v.get("dets", None)
            if raw_dets is None:
                raw_dets = v.get("detections", None)

            norm_dets = self._normalize_dets(raw_dets, gi)

            clean_views.append(
                {
                    "name": name,
                    # ✅ keep BOTH keys so any frontend version works
                    "dets": norm_dets,
                    "detections": norm_dets,
                    # keep jpg if provided (for hub.get_view_jpg usage)
                    "jpg": v.get("jpg", None),
                    # store gi for debugging
                    "gi": gi,
                }
            )

        with self._lock:
            self._cams[cam_id] = {
                "updated_at": now,
                "views": clean_views,
                "lost_items": lost_items or [],
            }

    def snapshot(self) -> Dict[str, Any]:
        """
        JSON-safe snapshot: remove jpg bytes from output.
        """
        with self._lock:
            out: Dict[str, Any] = {}
            for cam_id, data in self._cams.items():
                views = []
                for v in data.get("views", []):
                    views.append(
                        {
                            "name": v.get("name", "View"),
                            # ✅ always return both keys
                            "dets": v.get("dets", v.get("detections", [])) or [],
                            "detections": v.get("detections", v.get("dets", [])) or [],
                            "gi": v.get("gi", 0),
                        }
                    )

                out[cam_id] = {
                    "updated_at": data.get("updated_at"),
                    "views": views,
                    "lost_items": data.get("lost_items", []) or [],
                }
            return out

    def get_view_jpg(self, cam_id: str, view_idx: int) -> Optional[bytes]:
        with self._lock:
            cam = self._cams.get(cam_id)
            if not cam:
                return None

            views = cam.get("views", [])
            if not isinstance(views, list):
                return None

            if view_idx < 0 or view_idx >= len(views):
                return None

            jpg = views[view_idx].get("jpg", None)
            if isinstance(jpg, (bytes, bytearray)):
                return bytes(jpg)

            return None
