"""Merge check of an event cluster (report only, writes events/<id>/notes/merge_check.txt).

Usage: python scripts/event/04_merge_check.py --event <event_id>
1. 5 km cells over the members: first detection per cell; flags cells lit before the seed.
2. Front jumps: members of a pass farther than JUMP_KM from every member of earlier passes.
3. Neighbouring clusters within NEIGHBOUR_KM of the member bounding box, with first detection.
4. Robustness: seed and cluster size for other grid cell sizes.
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.event import event_dirs, parse_event_arg, select_event  # noqa: E402
from lib.helpers import KM_PER_DEG_LAT, dist_km, grid_clusters, grow_box, in_box, read_clean  # noqa: E402

MERGE_CELL_KM = 5.0
JUMP_KM = 10.0
NEIGHBOUR_KM = 15.0
ROBUSTNESS_CELLS_KM = [0.5, 1.0, 2.0]

event_id = parse_event_arg()
buf = io.StringIO()
with redirect_stdout(buf):
    sel = select_event(event_id)
    df, seed = sel["df"], sel["seed"]
    m = df[df["event_member"]].sort_values("obs_time_utc").copy()
    lat0 = m["latitude"].mean()
    print(f"event {event_id}: cluster {sel['cluster_id']}, {len(m)} members, seed {seed['platform']} "
          f"{seed['obs_time_utc']} at {seed['latitude']:.4f}, {seed['longitude']:.4f}")

    # 1. 5 km cells
    m["cy"] = np.floor(m["latitude"] * KM_PER_DEG_LAT / MERGE_CELL_KM).astype(int)
    m["cx"] = np.floor(m["longitude"] * KM_PER_DEG_LAT * np.cos(np.radians(lat0)) / MERGE_CELL_KM).astype(int)
    cells = (m.groupby(["cy", "cx"])
             .agg(first_utc=("obs_time_utc", "min"), last_utc=("obs_time_utc", "max"), n=("latitude", "size"),
                  lat=("latitude", "mean"), lon=("longitude", "mean"), first_platform=("platform", "first"))
             .reset_index().sort_values("first_utc"))
    cells["dist_seed_km"] = dist_km(seed["latitude"], seed["longitude"], cells["lat"].to_numpy(), cells["lon"].to_numpy())
    cells["before_seed"] = cells["first_utc"] < seed["obs_time_utc"]
    cells["hours_after_seed"] = (cells["first_utc"] - seed["obs_time_utc"]).dt.total_seconds() / 3600
    print(f"\n1. {MERGE_CELL_KM:g} km cells: {len(cells)}; lit before the seed: {int(cells['before_seed'].sum())}")
    print(cells[["first_utc", "first_platform", "hours_after_seed", "n", "lat", "lon", "dist_seed_km", "last_utc"]]
          .round({"lat": 3, "lon": 3, "dist_seed_km": 1, "hours_after_seed": 1}).to_string(index=False))

    # 2. front jumps between consecutive passes
    print(f"\n2. front jumps (> {JUMP_KM:g} km from every member of earlier passes):")
    passes = m.groupby("overpass_id")["obs_time_utc"].min().sort_values()
    earlier = m[m["overpass_id"] == passes.index[0]]
    n_jumps = 0
    for oid in passes.index[1:]:
        g = m[m["overpass_id"] == oid]
        dmin = np.array([dist_km(r.latitude, r.longitude, earlier["latitude"].to_numpy(),
                                 earlier["longitude"].to_numpy()).min() for r in g.itertuples()])
        far = g[dmin > JUMP_KM]
        if len(far):
            n_jumps += 1
            print(f"  {oid} {passes[oid]}: {len(far)} of {len(g)} members jump, nearest earlier member "
                  f"{dmin[dmin > JUMP_KM].min():.1f} km; jumped pixels centre {far['latitude'].mean():.3f}, "
                  f"{far['longitude'].mean():.3f}")
        earlier = pd.concat([earlier, g])
    print(f"  passes with a jump: {n_jumps} of {len(passes) - 1}")
    print("  largest step per pass (km, nearest earlier member, max over the pass members) is in the table above "
          "only when it exceeds the threshold")

    # 3. neighbouring clusters
    near_box = grow_box({"lat_min": m["latitude"].min(), "lat_max": m["latitude"].max(),
                         "lon_min": m["longitude"].min(), "lon_max": m["longitude"].max()}, NEIGHBOUR_KM / KM_PER_DEG_LAT)
    nb = df[in_box(df, near_box) & ~df["event_member"]]
    nbc = (nb.groupby("fire_cluster")
           .agg(n=("latitude", "size"), first_utc=("obs_time_utc", "min"), last_utc=("obs_time_utc", "max"),
                lat=("latitude", "mean"), lon=("longitude", "mean"))
           .sort_values("n", ascending=False))
    nbc["gap_to_event_km"] = [dist_km(r.lat, r.lon, m["latitude"].to_numpy(), m["longitude"].to_numpy()).min()
                              for r in nbc.itertuples()]
    print(f"\n3. other clusters within about {NEIGHBOUR_KM:g} km of the member bounding box: {len(nbc)} "
          f"({len(nb)} detections); with >= 10 detections:")
    print(nbc[nbc["n"] >= 10].round({"lat": 3, "lon": 3, "gap_to_event_km": 1}).to_string())

    # 4. robustness to the grid cell
    print("\n4. robustness to the cluster grid cell:")
    base = read_clean(sel["event"]["region"])
    for cell in ROBUSTNESS_CELLS_KM:
        base["cl_test"] = grid_clusters(base["latitude"].to_numpy(), base["longitude"].to_numpy(), cell)
        s = select_event(event_id, df=base, cluster_col="cl_test")
        mm = s["df"][s["df"]["event_member"]]
        print(f"  cell {cell:g} km: seed {s['seed']['platform']} {s['seed']['obs_time_utc']} "
              f"({s['seed']['latitude']:.4f}, {s['seed']['longitude']:.4f}); {len(mm)} members, "
              f"{mm['obs_time_utc'].min()} to {mm['obs_time_utc'].max()}, lat {mm['latitude'].min():.3f} to "
              f"{mm['latitude'].max():.3f}, lon {mm['longitude'].min():.3f} to {mm['longitude'].max():.3f}; "
              f"members before earliest accepted time: {s['n_members_before_earliest']}")

report = buf.getvalue()
print(report)
(event_dirs(event_id)["notes"] / "merge_check.txt").write_text(report)
