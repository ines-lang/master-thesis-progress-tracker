"""Seed selection and event cluster report (no products written).

Usage: python scripts/event/01_select.py --event <event_id>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.event import parse_event_arg, select_event  # noqa: E402
from lib.helpers import extent_km  # noqa: E402

event_id = parse_event_arg()
sel = select_event(event_id)
ev, df, seed, t0 = sel["event"], sel["df"], sel["seed"], sel["t0"]
m = df[df["event_member"]]

print(f"event: {event_id} ({ev['name']})")
print(f"ignition_utc {sel['ignition']}, tolerance {ev['ignition_tolerance_min']} min, earliest accepted {sel['earliest']}")
print(f"reference_point {ev['reference_point']['lat']}, {ev['reference_point']['lon']}, seed radius {ev['seed_radius_km']} km")
print(f"\nseed: {seed['platform']} {seed['obs_time_utc']} at {seed['latitude']:.4f}, {seed['longitude']:.4f}, "
      f"{seed['dist_ref_km']:.2f} km from reference, FRP {seed['frp']} MW, qc {seed['qc_flag']}")
print(f"seed relative to stated ignition: {(seed['obs_time_utc'] - sel['ignition']).total_seconds() / 60:+.0f} min "
      f"({'BEFORE' if seed['obs_time_utc'] < sel['ignition'] else 'at or after'} the stated ignition)")
print(f"T0 candidate: {t0['platform']} {t0['obs_time_utc']} ({t0['sensor']})")
print(f"\ncluster {sel['cluster_id']}: {len(m)} detections, {m['obs_time_utc'].min()} to {m['obs_time_utc'].max()}")
print(f"  centre {m['latitude'].mean():.3f}, {m['longitude'].mean():.3f}; bbox lat {m['latitude'].min():.3f} to "
      f"{m['latitude'].max():.3f}, lon {m['longitude'].min():.3f} to {m['longitude'].max():.3f}; "
      f"diagonal {extent_km(m['latitude'], m['longitude']):.1f} km")
print(f"  members before earliest accepted time: {sel['n_members_before_earliest']}")
print(f"  members inside search box: {m['in_search_box'].sum()} of {len(m)}")
print("  by platform:", m.groupby("platform").size().to_dict())
print("  qc_flag:", m["qc_flag"].value_counts().to_dict())
