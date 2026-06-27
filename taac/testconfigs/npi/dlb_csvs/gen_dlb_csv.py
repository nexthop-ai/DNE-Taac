#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""IcePack DLB CSV generator — IXIA add-path (prefix, next-hop) upload files.

Produces the *DLB-side* CSVs only. ECMP (Silver/Rouge) stays FORMULAIC
(`CustomNetworkGroupConfig` multiplier/width, per Sriram's
`wedge400_ecmp_resource_testing_config.py`) — do NOT enumerate ECMP here.

Hardware model (TH6/IcePack `gtsw001`, confirmed live 2026-06-24):
  - `getMaxArsWidth()  = 64`  ← MEMBERS per single ARS super-group (silicon)
  - `getMaxArsGroups() = 128` ← number of ARS group slots on chip
  - `getMaxEcmpMembers() = 128000` (global ECMP member table)
  - Plus device-wide "Virtual ARS supergroup unique member" budget that
    sums across all ARS supergroups — spine ARS state consumes part of
    it, so the spine-disable patcher must run BEFORE bgpd FIB sync.

For DISTINCT-supergroup tests (the whole point of fill_511): every
prefix MUST have a DIFFERENT NH subset, otherwise FBOSS Agent's
EcmpResourceManager DEDUPLICATES same-NH-set prefixes into ONE shared
ARS supergroup (verified empirically gtsw001 2026-06-24 23:13 — 511
prefixes with the same 64 NHs collapsed to 1 ARS supergroup, ECMP
member count: 64). To actually hit the 128-group cap and observe
spillover, each prefix's NH set must be unique.

CSV format (matches the IXIA sample `ixia_data_upload_*.csv`): full
8-hextet IPv6, no leading zeros, no `::` compression. Header:
`Address,Ipv6 Next Hop`. Same Address on N rows = an N-wide ECMP group
formed once IxNetwork advertises via add-path. Different prefixes with
DIFFERENT NH subsets => distinct ECMP groups on silicon. Different
prefixes with the SAME NH subset => dedup'd to ONE shared group.

Outputs (default `./csv`):
  dlb_fill_511.csv    511 prefixes × 64 DISTINCT NH subsets of 128 NHs  → 511 distinct ARS groups (TC211 group-spillover)
  dlb_members_128.csv groups whose union = all 128 unique NHs            → TC215 (fill DLB members)
  dlb_width_64.csv    1 group × 64 NHs (TH6 silicon max width)           → TC221
  dlb_overflow_129.csv 128 unique + a 129th NH (a081) → must spill/reject → TC212 / TC213

Usage:
  python3 gen_dlb_csv.py                       # defaults: 511 groups, width 64, 128 NHs
  python3 gen_dlb_csv.py --groups 512          # group-count spillover (512th group) → TC213
  python3 gen_dlb_csv.py --out /path/to/dir
"""

import argparse
import csv
import ipaddress
import os

# ---- Addressing (from testconfigs/icepack/be_qos_schd_buffering_test_config.py + CSV sample) ----
NH_NETWORK = (
    "2401:db00:206a:c002"  # uplink NH-supporting /64 (the 130-iface DG lives here)
)
NH_HOST_START = 0xA001  # first NH host → ::a001
DLB_PREFIX_NET = "5000:dd"  # advertised DLB (Gold) prefixes → 5000:dd:0:N::


def fmt(addr: str) -> str:
    """Full 8-hextet, no leading zeros, no `::` — matches the IXIA upload sample."""
    return ":".join(
        f"{int(g, 16):x}" for g in ipaddress.IPv6Address(addr).exploded.split(":")
    )


def nh(i: int) -> str:
    """i-th next-hop address: ::a001, ::a002, ... (i=128 → a081 overflow spare)."""
    return fmt(f"{NH_NETWORK}::{NH_HOST_START + i:x}")


def prefix(n: int) -> str:
    """n-th advertised DLB prefix: 5000:dd:0:n::"""
    return fmt(f"{DLB_PREFIX_NET}:0:{n:x}::")


def write_csv(path: str, rows) -> int:
    # `lineterminator="\n"`: csv.writer defaults to "\r\n" (Windows
    # CRLF). IxNetwork's ImportBgpRoutes accepts either, but the TAAC
    # `ixia.py::import_bgp_routes` wrapper re-chunks the CSV server-side
    # and treats "\n" as the row separator — keeping the source LF-only
    # avoids the need for CRLF normalisation downstream.
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Address", "Ipv6 Next Hop"])
        w.writerows(rows)
    return len(rows)


def _included_set(g: int, width: int, nh_count: int) -> frozenset:
    """A distinct `width`-NH subset for prefix g, drawn from `nh_count`
    candidates via seeded RNG.

    The earlier mod-arithmetic generator (`base = g*7 % nh_count, step
    = 1 + g // nh_count`) collapsed in tier 2 (step=2 partitioned
    {0..127} into evens vs odds → only 2 distinct sets per tier). RNG
    approach guarantees uniqueness for any `groups <= C(nh_count,
    width)` — for our defaults (C(128,64) ≈ 2.4e37) collisions are
    statistically impossible for 511 groups. Caller wraps a
    deduplicating `while incl in seen: g += nh_count` fallback as a
    belt-and-braces safety net.

    Why include (not exclude): with TH6 `getMaxArsWidth()=64`, the
    INCLUDE side is the small dimension (64 of 128). Earlier
    `_excluded_set` form used 8-of-128 excludes for 120-wide groups
    (assumed 128-wide silicon support; TH6 reality is width=64).
    """
    import random

    rng = random.Random(g)
    return frozenset(rng.sample(range(nh_count), width))


def gen_fill(groups: int, width: int, nh_count: int):
    """`groups` DISTINCT `width`-wide NH subsets of `nh_count` NHs.

    Each prefix gets its OWN unique NH subset → each becomes a distinct
    ECMP group on FBOSS Agent (no dedup by EcmpResourceManager). Union
    of all subsets covers all nh_count NHs (so the super-group both
    reaches `groups` distinct groups AND fills the member pool).

    With TH6 (width=64, groups=511): produces 511 distinct 64-NH subsets
    of the 128-NH pool. C(128,64) ≈ 2.4e37 — distinctness via the
    rotating-start + per-tier-stride algorithm is guaranteed for any
    groups ≤ nh_count^2 (which 511 << 128² = 16384 easily satisfies).
    """
    rows, seen = [], set()
    for g in range(groups):
        incl = _included_set(g, width, nh_count)
        bump = 0
        while (
            incl in seen
        ):  # guarantee distinct NH-sets (=> distinct ECMP groups on silicon)
            bump += 1
            incl = _included_set(g + bump * nh_count, width, nh_count)
        seen.add(incl)
        for i in sorted(incl):
            rows.append((prefix(g), nh(i)))
    return rows


def gen_members(nh_count: int, width: int):
    """Minimal groups whose union = all nh_count unique NHs (isolates the
    member dimension)."""
    rows = []
    g = 0
    covered = 0
    start = 0
    while covered < nh_count:
        ids = [i % nh_count for i in range(start, start + width)]
        for i in ids:
            rows.append((prefix(g), nh(i)))
        covered = max(covered, start + width)
        start += width
        g += 1
    return rows


def gen_width(width: int = 64):
    """One group using `width` NHs (TH6 silicon max width = 64)."""
    return [(prefix(0), nh(i)) for i in range(width)]


def gen_overflow(width: int, nh_count: int):
    """Fill the nh_count pool, then add one group that introduces the
    (nh_count+1)-th unique NH → projected unique = nh_count+1 > limit →
    must spill to ECMP / be rejected."""
    rows = gen_members(nh_count, width)  # nh_count unique present
    overflow_group = nh_count  # the (nh_count+1)-th NH (index 128 → a081)
    ids = [overflow_group] + list(range(width - 1))
    rows += [(prefix(900), nh(i)) for i in ids]
    return rows


# ---------------------------------------------------------------------------
# Community sidecar CSV — needed because the GTSW `PROPAGATE_GTSW_STSW_IN`
# policy chain gates FIB install on 3 specific community values. Verified
# missing-community failure mode on gtsw001.l1001.c085.ash6 (2026-06-23
# pilot V1): peer ESTABLISHED + PR=1, PA=0. Format is no-header,
# comma-separated AS:Value pairs per row; IXIA round-robins through them.
# A single row applies to all advertised routes uniformly.
#
#   65446:30   — LIVE: rule 1 sets LP=100
#   65441:323  — PATH_COMMUNITY_GTSW_E_HOP3 (rule 4 DENY on miss)
#   65456:323  — LP=90 marker (rule 17 DENY on miss)
# ---------------------------------------------------------------------------
GTSW_GATING_COMMUNITIES: tuple = ("65446:30", "65441:323", "65456:323")


def write_communities_csv(path: str, communities: tuple = GTSW_GATING_COMMUNITIES):
    """Write a 1-row community CSV.

    Format expected by `ixia.py::_parse_communities_file`:
    `AS,LastTwoOctets,AS,LastTwoOctets,...` (pairs of comma-separated
    fields, NOT `AS:LastTwoOctets` colon-separated). The parser does
    `row.split(",")` then walks pairwise. A single row applies to all
    advertised routes uniformly under round-robin distribution.
    """
    flat: list[str] = []
    for c in communities:
        as_num, octets = c.split(":")
        flat.append(as_num)
        flat.append(octets)
    with open(path, "w") as f:
        f.write(",".join(flat) + "\n")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv"),
    )
    ap.add_argument("--groups", type=int, default=511)
    # TH6 silicon cap: getMaxArsWidth() = 64 (members per single ARS group).
    # See Tomahawk6Asic.cpp:278-290 and gtsw001 empirical verification
    # 2026-06-24 (P2395075725). Earlier default of 120 was based on the
    # (wrong) assumption that TH6 supports 128 members per ARS group.
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--nh-count", type=int, default=128)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    jobs = {
        # TH6-cap test: 511 prefixes × 64-NH subsets. Each prefix fits in
        # one ARS group (`getMaxArsWidth=64`); first 128 prefixes fill the
        # ARS group slots, remaining 383 spill to non-ARS ECMP.
        "dlb_fill_511_w64.csv": gen_fill(a.groups, 64, a.nh_count),
        # TH6-cap-stress test: 511 prefixes × 120-NH subsets. Each prefix
        # is wider than `getMaxArsWidth=64`; expect either (a) per-prefix
        # truncate to 64, (b) virtual ARS supergroup stacking (2 slots
        # each = max 64 prefixes), or (c) rejection. Both data points
        # together definitively characterise the per-group cap.
        "dlb_fill_511_w120.csv": gen_fill(a.groups, 120, a.nh_count),
        "dlb_members_128.csv": gen_members(a.nh_count, a.width),
        "dlb_width_64.csv": gen_width(a.width),
        "dlb_overflow_129.csv": gen_overflow(a.width, a.nh_count),
    }
    for name, rows in jobs.items():
        n = write_csv(os.path.join(a.out, name), rows)
        groups = len({r[0] for r in rows})
        nhs = len({r[1] for r in rows})
        print(f"{name:24s} rows={n:>7d}  groups={groups:>4d}  unique_nh={nhs:>4d}")
    print(f"\nWrote to {a.out}  (DLB only; ECMP stays formulaic — see KB blueprint)")


if __name__ == "__main__":
    main()
