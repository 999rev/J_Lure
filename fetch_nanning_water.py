"""
fetch_nanning_water.py
一次性分块抓取南宁全境（含邕江、良凤江、大王滩、蒲庙、凤亭河等）水系、桥梁与闸坝，
预计算结构标点并保存为极轻量的 data/nanning_hotspots.json，供网页端毫秒级加载。

运行方式（在 J_Lure 目录下，使用已有 httpx 的 Python 环境）：
    python fetch_nanning_water.py
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

import httpx

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# 覆盖南宁主城区 + 良凤江 + 大王滩 + 邕宁/蒲庙 + 武鸣南部
LAT_STEPS = [22.55, 22.72, 22.89, 23.06]
LON_STEPS = [108.05, 108.25, 108.45, 108.65]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def seg_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> tuple[float, float] | None:
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def turning_angle_deg(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    v1x, v1y = b[1] - a[1], b[0] - a[0]
    v2x, v2y = c[1] - b[1], c[0] - b[0]
    n1, n2 = math.hypot(v1x, v1y), math.hypot(v2x, v2y)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos_val = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (n1 * n2)))
    return math.degrees(math.acos(cos_val))


def unit_vec(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[1] - a[1], b[0] - a[0]
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return (1.0, 0.0)
    return (round(dx / n, 3), round(dy / n, 3))


def fetch_bbox(s: float, w: float, n: float, e: float) -> dict:
    query = f"""
    [out:json][timeout:45];
    (
      way["waterway"~"river|stream|canal"]({s},{w},{n},{e});
      way["bridge"="yes"]["highway"~"motorway|trunk|primary|secondary|tertiary"]({s},{w},{n},{e});
      node["waterway"~"weir|dam"]({s},{w},{n},{e});
      way["natural"="water"]({s},{w},{n},{e});
    );
    out geom;
    """
    headers = {
        "User-Agent": "castwindow-static-builder/1.0",
        "Accept": "application/json, text/plain, */*",
    }
    last_err: Exception | None = None
    for ep in ENDPOINTS:
        try:
            resp = httpx.post(ep, data={"data": query}, headers=headers, timeout=60.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_err = exc
            time.sleep(1.0)
    raise RuntimeError(f"网格 ({s},{w},{n},{e}) 拉取失败: {last_err}")


def extract_spots(osm_data: dict) -> list[dict]:
    nodes: dict[int, tuple[float, float]] = {}
    waterways: list[dict] = []
    bridges: list[dict] = []
    weirs: list[dict] = []
    water_polys: list[dict] = []

    for el in osm_data.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
            if el.get("tags", {}).get("waterway") in {"weir", "dam"}:
                weirs.append(el)
        elif el["type"] == "way":
            geom = el.get("geometry", [])
            nids = el.get("nodes", [])
            for nid, pt in zip(nids, geom):
                nodes[nid] = (pt["lat"], pt["lon"])
            tags = el.get("tags", {})
            if "waterway" in tags:
                waterways.append(el)
            if tags.get("bridge") == "yes":
                bridges.append(el)
            if tags.get("natural") == "water" and len(geom) >= 12:
                water_polys.append(el)

    spots: list[dict] = []

    # 1. 支流交汇口
    node_ways: dict[int, list[str]] = defaultdict(list)
    for w in waterways:
        w_name = w.get("tags", {}).get("name") or w.get("tags", {}).get("waterway", "河道")
        for nid in set(w.get("nodes", [])):
            node_ways[nid].append(w_name)
    for nid, names in node_ways.items():
        if len(names) >= 2 and nid in nodes:
            lat, lon = nodes[nid]
            spots.append({
                "k": "支流交汇口",
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "base": 82,
                "dx": 1.0,
                "dy": 0.0,
                "desc": f"水系交汇 ({' + '.join(set(names))})，溶氧与饵鱼密集",
            })

    # 2. 闸坝
    for wn in weirs:
        spots.append({
            "k": "拦水坝/闸口",
            "lat": round(wn["lat"], 5),
            "lon": round(wn["lon"], 5),
            "base": 80,
            "dx": 1.0,
            "dy": 0.0,
            "desc": "跌水洄流区，溶氧高且下泄饵鱼集中",
        })

    # 3. 桥梁跨河结构
    for b in bridges:
        b_pts = [nodes[nid] for nid in b.get("nodes", []) if nid in nodes]
        b_name = b.get("tags", {}).get("name", "跨河桥梁")
        for w in waterways:
            w_pts = [nodes[nid] for nid in w.get("nodes", []) if nid in nodes]
            for i in range(len(b_pts) - 1):
                for j in range(len(w_pts) - 1):
                    hit = seg_intersect(b_pts[i], b_pts[i + 1], w_pts[j], w_pts[j + 1])
                    if hit:
                        dx, dy = unit_vec(w_pts[j], w_pts[j + 1])
                        spots.append({
                            "k": "桥梁跨河结构",
                            "lat": round(hit[0], 5),
                            "lon": round(hit[1], 5),
                            "base": 68,
                            "dx": dx,
                            "dy": dy,
                            "desc": f"{b_name} 桥墩阴影与洄水",
                        })

    # 4. 河道急弯
    for w in waterways:
        w_pts = [nodes[nid] for nid in w.get("nodes", []) if nid in nodes]
        w_name = w.get("tags", {}).get("name", "河道")
        for i in range(1, len(w_pts) - 1):
            ang = turning_angle_deg(w_pts[i - 1], w_pts[i], w_pts[i + 1])
            if ang >= 32.0:
                dx, dy = unit_vec(w_pts[i - 1], w_pts[i + 1])
                spots.append({
                    "k": "河道急弯",
                    "lat": round(w_pts[i][0], 5),
                    "lon": round(w_pts[i][1], 5),
                    "base": 62 + min(8, int(ang // 12)),
                    "dx": dx,
                    "dy": dy,
                    "desc": f"{w_name} {ang:.0f}° 弯道深槽/缓水区",
                })

    # 5. 水库/湖泊岸线铧尖（凸向水面）与凹湾（凹入陆地）
    for wp in water_polys:
        geom = wp.get("geometry", [])
        pts = [(pt["lat"], pt["lon"]) for pt in geom]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 12:
            continue

        # 计算有向面积判断多边形绕向（CCW > 0, CW < 0）
        area2 = 0.0
        n_pts = len(pts)
        for i in range(n_pts):
            y1, x1 = pts[i]
            y2, x2 = pts[(i + 1) % n_pts]
            area2 += x1 * y2 - x2 * y1
        if abs(area2) < 1e-9:
            continue

        w_name = wp.get("tags", {}).get("name", "水库/湖泊")
        for i in range(n_pts):
            a = pts[(i - 1) % n_pts]
            b = pts[i]
            c = pts[(i + 1) % n_pts]
            if haversine_m(a[0], a[1], b[0], b[1]) < 15.0 or haversine_m(b[0], b[1], c[0], c[1]) < 15.0:
                continue
            ang = turning_angle_deg(a, b, c)
            if ang < 38.0 or ang > 150.0:
                continue
            cross = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
            dx, dy = unit_vec(a, c)
            is_headland = (cross * area2) < 0
            if is_headland:
                spots.append({
                    "k": "水库铧尖",
                    "lat": round(b[0], 5),
                    "lon": round(b[1], 5),
                    "base": 74 + min(8, int(ang // 15)),
                    "dx": dx,
                    "dy": dy,
                    "desc": f"{w_name} 突出铧尖（转向 {ang:.0f}°），鱼群巡游必经通道",
                })
            else:
                spots.append({
                    "k": "水库凹湾",
                    "lat": round(b[0], 5),
                    "lon": round(b[1], 5),
                    "base": 70 + min(6, int(ang // 18)),
                    "dx": dx,
                    "dy": dy,
                    "desc": f"{w_name} 避风凹湾（转向 {ang:.0f}°），聚饵鱼与浅滩结构区",
                })

    return spots


def main() -> None:
    all_spots: list[dict] = []
    total_cells = (len(LAT_STEPS) - 1) * (len(LON_STEPS) - 1)
    cell_idx = 0

    for i in range(len(LAT_STEPS) - 1):
        for j in range(len(LON_STEPS) - 1):
            cell_idx += 1
            s, n = LAT_STEPS[i], LAT_STEPS[i + 1]
            w, e = LON_STEPS[j], LON_STEPS[j + 1]
            print(f"[{cell_idx}/{total_cells}] 正在抓取网格 ({s:.2f},{w:.2f}) -> ({n:.2f},{e:.2f})...")
            data = fetch_bbox(s, w, n, e)
            cell_spots = extract_spots(data)
            print(f"    提取到 {len(cell_spots)} 个候选点")
            all_spots.extend(cell_spots)
            time.sleep(1.0)

    # 全局去重（80m 内保留最高基础分）
    deduped: list[dict] = []
    for sp in sorted(all_spots, key=lambda x: x["base"], reverse=True):
        if all(haversine_m(sp["lat"], sp["lon"], d["lat"], d["lon"]) > 80.0 for d in deduped):
            deduped.append(sp)

    out_path = Path("data/nanning_hotspots.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(deduped, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n全部完成！共保存 {len(deduped)} 个南宁标点至 {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
