#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""
Inject IPv6 prefixes into BGP++ on a GTSW via the thrift addNetworks API,
then validate the injection by querying the BGP RIB.

Workflow:
  1. Connect to the GTSW via FbossSwitchInternal (ServiceRouter-backed
     thrift client to bgpd).
  2. Build a TIpPrefix from the CIDR string and a list of TBgpCommunity
     from the "ASN:VALUE" community strings.
  3. Wrap into TBgpAttributes and call addNetworks() via the helper
     accessor `await device.bgp().async_add_networks(...)`.
  4. Validate:
       a. getRibPrefix(prefix) -> exactly 1 TRibEntry for the injected prefix.
       b. getRibEntriesForCommunities(AFI_IPV6, [community...]) -> the
          injected prefix appears (community filter is OR-match).
  5. Optionally `--cleanup` to delNetworks() the same prefix at the end.

Defaults match the user's request for MWG2 FPF testing:
  device:   gtsw001.l1002.c087.mwg2
  prefix:   5000:dd::/64
  communities: 65441:2241, 65441:2305, 65442:2243, 65442:2308,
               65446:30, 65446:102, 65455:2308, 65456:2243,
               65456:2307, 65457:2241, 65457:2242, 65457:2305,
               65457:2306, 65529:52792

Usage:
  # Single prefix, defaults
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2

  # Explicit list of prefixes
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2 \\
    --prefixes 5000:dd::/64,5000:dd:1::/64,5000:dd:2::/64

  # Range of 16 prefixes: 5000:dd::, 5000:dd:1::, ... 5000:dd:f:: /64
  # --increment-step is an IPv6 with a 1 in the hextet to advance.
  # '0:0:1::' = increment the 3rd hextet (default).
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2 \\
    --prefix-base 5000:dd::/64 --count 16 --increment-step 0:0:1::

  # Withdraw-only mode (no injection, no validation)
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2 \\
    --prefix-base 5000:dd::/64 --count 16 --increment-step 0:0:1:: \\
    --withdraw

  # Inject + validate + cleanup at the end
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2 \\
    --prefix 5000:dd::/64 --cleanup

  # Inject on gtsw001 (= lane 0) and assert via HRT on the GPU host that
  # the prefix is visible on plane 0 ONLY for device 0
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2 \\
    --prefix-base 5000:dd::/64 --count 16 \\
    --validate-hrt-host rtptest1544.mwg2 \\
    --validate-hrt-device-id 0

  # Use the built-in STSW community preset (PATH_COMMUNITY_STSW_*_HOP2)
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device stsw001.s001.l202.mwg2 \\
    --prefix-base 5000:dd::/64 --count 16 \\
    --community-list stsw

  # Use the built-in GTSW community preset (PATH_COMMUNITY_GTSW_*_HOP1)
  buck2 run fbcode//scripts/pavanpatil:inject_bgp_prefixes -- \\
    --device gtsw001.l1002.c087.mwg2 \\
    --prefix-base 5000:dd::/64 --count 16 \\
    --community-list gtsw
"""

import argparse
import asyncio
import io
import ipaddress
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, TextIO

from neteng.fboss.bgp_attr.types import TBgpAfi, TBgpCommunity, TIpPrefix
from neteng.fboss.bgp_route_types.types import TRibEntry
from neteng.fboss.bgp_thrift.types import TBgpAttributes
from neteng.netcastle.logger import get_root_logger
from neteng.netcastle.utils.everpaste_utils import async_everpaste_str
from taac.internal.driver.fboss_switch_internal import (
    FbossSwitchInternal,
)
from taac.libs.fpf.fpf_fsdb_ribmap import (
    get_fsdb_rib_map,
    parse_rib_map_communities,
)
from taac.libs.fpf.fpf_hrt_polling import get_hrt_client


logger = get_root_logger()


DEFAULT_DEVICE = "gtsw001.l1002.c087.mwg2"
DEFAULT_PREFIX = "5000:dd::/64"

# Preset community lists, named by originating device role. Only the
# PATH_COMMUNITY (ASN 65441) values differ between sets — the remaining
# 12 communities (STOP, LOCAL_PREF, LIVE, WARM_NO_PROP, VIP) are shared.
GTSW_COMMUNITIES = [
    "65441:2241",  # PATH_COMMUNITY_GTSW_AI_HOP1
    "65441:2305",  # PATH_COMMUNITY_GTSW_AJ_HOP1
    "65442:2243",  # STOP_COMMUNITY_GTSW_AI_HOP3
    "65442:2308",  # STOP_COMMUNITY_GTSW_AJ_HOP4
    "65446:30",  # LIVE
    "65446:102",  # WARM_NO_PROP
    "65455:2308",  # LOCAL_PREF_80_AJ_HOP4
    "65456:2243",  # LOCAL_PREF_90_AI_HOP3
    "65456:2307",  # LOCAL_PREF_90_AJ_HOP3
    "65457:2241",  # LOCAL_PREF_100_AI_HOP1
    "65457:2242",  # LOCAL_PREF_100_AI_HOP2
    "65457:2305",  # LOCAL_PREF_100_AJ_HOP1
    "65457:2306",  # LOCAL_PREF_100_AJ_HOP2
    "65529:52792",  # AI_ZONE_LB_HOST_VIP
]

STSW_COMMUNITIES = [
    "65441:2242",  # PATH_COMMUNITY_STSW_AI_HOP2  (differs from GTSW)
    "65441:2306",  # PATH_COMMUNITY_STSW_AJ_HOP2  (differs from GTSW)
    "65442:2243",  # STOP_COMMUNITY_GTSW_AI_HOP3
    "65442:2308",  # STOP_COMMUNITY_GTSW_AJ_HOP4
    "65446:30",  # LIVE
    "65446:102",  # WARM_NO_PROP
    "65455:2308",  # LOCAL_PREF_80_AJ_HOP4
    "65456:2243",  # LOCAL_PREF_90_AI_HOP3
    "65456:2307",  # LOCAL_PREF_90_AJ_HOP3
    "65457:2241",  # LOCAL_PREF_100_AI_HOP1
    "65457:2242",  # LOCAL_PREF_100_AI_HOP2
    "65457:2305",  # LOCAL_PREF_100_AJ_HOP1
    "65457:2306",  # LOCAL_PREF_100_AJ_HOP2
    "65529:52792",  # AI_ZONE_LB_HOST_VIP
]

COMMUNITY_PRESETS = {
    "gtsw": GTSW_COMMUNITIES,
    "stsw": STSW_COMMUNITIES,
}

# Backward-compat for any external callers.
DEFAULT_COMMUNITIES = GTSW_COMMUNITIES


# ---------------------------------------------------------------------------
# Thrift type builders
# ---------------------------------------------------------------------------


def build_tip_prefix(cidr: str) -> TIpPrefix:
    """Build a TIpPrefix struct from a CIDR string like '5000:dd::/64'."""
    network = ipaddress.ip_network(cidr, strict=False)
    if isinstance(network, ipaddress.IPv6Network):
        afi = TBgpAfi.AFI_IPV6
    elif isinstance(network, ipaddress.IPv4Network):
        afi = TBgpAfi.AFI_IPV4
    else:
        raise ValueError(f"Unsupported network type: {type(network)}")
    return TIpPrefix(
        afi=afi,
        prefix_bin=network.network_address.packed,
        num_bits=network.prefixlen,
    )


def prefix_to_str(prefix: TIpPrefix) -> str:
    """Render a TIpPrefix back to canonical 'ip/mask' for display."""
    ip = ipaddress.ip_address(prefix.prefix_bin).compressed
    return f"{ip}/{prefix.num_bits}"


def parse_community(community_str: str) -> TBgpCommunity:
    """Parse 'ASN:VALUE' into a TBgpCommunity."""
    parts = community_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Bad community '{community_str}' — expected 'ASN:VALUE'")
    try:
        asn = int(parts[0])
        value = int(parts[1])
    except ValueError as e:
        raise ValueError(f"Non-integer community '{community_str}'") from e
    return TBgpCommunity(asn=asn, value=value)


def build_communities(community_strs: Sequence[str]) -> List[TBgpCommunity]:
    return [parse_community(c) for c in community_strs]


def parse_increment_step(step_str: str) -> int:
    """Parse an IPv6 address used as an increment-step into an integer delta.

    The step is expressed as an IPv6 with a 1 in whichever hextet you want
    to advance. Examples:
      '0:0:1::'         -> increment 3rd hextet  (delta = 1 << 80)
      '0:0:0:1::'       -> increment 4th hextet  (delta = 1 << 64)
      '::1'             -> increment lowest hextet (delta = 1)
      '0:0:1:0:0:0:0:0' -> same as '0:0:1::'    (delta = 1 << 80)
    """
    addr = ipaddress.IPv6Address(step_str)
    delta = int(addr)
    if delta == 0:
        raise ValueError(
            f"--increment-step {step_str!r} is all zeros; nothing to increment"
        )
    return delta


def expand_prefix_range(base_cidr: str, count: int, increment_step: str) -> List[str]:
    """Expand a base CIDR into `count` prefixes, advancing the network
    address by `increment_step` (an IPv6 string) each iteration.

    For base '5000:dd::/64', count=16, increment_step='0:0:1::' this yields:
      5000:dd::/64, 5000:dd:1::/64, 5000:dd:2::/64, ... 5000:dd:f::/64
    """
    network = ipaddress.ip_network(base_cidr, strict=False)
    base_int = int(network.network_address)
    delta = parse_increment_step(increment_step)
    out = []
    for i in range(count):
        addr = ipaddress.ip_address(base_int + i * delta)
        out.append(f"{addr.compressed}/{network.prefixlen}")
    return out


# ---------------------------------------------------------------------------
# Injection + validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    rib_lookup_passed: bool
    rib_lookup_paths: int
    community_lookup_passed: bool
    community_lookup_prefix_found: bool


async def inject_prefixes(
    driver: FbossSwitchInternal,
    prefixes: Sequence[TIpPrefix],
    communities: Sequence[TBgpCommunity],
) -> None:
    """Bulk-inject prefixes with the same communities via a single addNetworks() call."""
    attrs = TBgpAttributes(communities=list(communities))
    networks = {p: attrs for p in prefixes}
    bgp = await driver.bgp()
    logger.info(
        f"[{driver.hostname}] Injecting {len(prefixes)} prefix(es) with "
        f"{len(communities)} communities via addNetworks(): "
        f"{', '.join(prefix_to_str(p) for p in prefixes[:5])}"
        f"{'...' if len(prefixes) > 5 else ''}"
    )
    await bgp.async_add_networks(networks)
    logger.info(f"[{driver.hostname}] addNetworks() returned OK")


async def withdraw_prefixes(
    driver: FbossSwitchInternal, prefixes: Sequence[TIpPrefix]
) -> None:
    """Bulk-withdraw prefixes via a single delNetworks() call."""
    bgp = await driver.bgp()
    logger.info(
        f"[{driver.hostname}] Withdrawing {len(prefixes)} prefix(es) via delNetworks(): "
        f"{', '.join(prefix_to_str(p) for p in prefixes[:5])}"
        f"{'...' if len(prefixes) > 5 else ''}"
    )
    await bgp.async_del_networks(list(prefixes))
    logger.info(f"[{driver.hostname}] delNetworks() returned OK")


def _entry_prefix_str(entry: TRibEntry) -> str:
    try:
        return prefix_to_str(entry.prefix)
    except Exception:
        return "<unparseable>"


def _normalize_prefix(prefix_str: str) -> Optional[str]:
    try:
        return str(ipaddress.ip_network(prefix_str, strict=False))
    except Exception:
        return None


def _index_rib_entries(entries) -> Dict[str, int]:
    """Build prefix-normalized -> path_count index from a TRibEntry list."""
    out: Dict[str, int] = {}
    for entry in entries:
        norm = _normalize_prefix(_entry_prefix_str(entry))
        if norm is None:
            continue
        out[norm] = len(entry.paths) if entry.paths else 0
    return out


async def validate_injection_bulk(
    driver: FbossSwitchInternal,
    injected_prefixes: Sequence[TIpPrefix],
    communities: Sequence[TBgpCommunity],
) -> List[ValidationResult]:
    """Validate all injected prefixes with TWO bulk thrift calls:

    1. getRibEntries(AFI_IPV6) -> full RIB; build {prefix: path_count} index.
    2. getRibEntriesForCommunities(AFI_IPV6, [all]) -> community-filtered RIB;
       build set of prefixes.

    Then check each injected prefix against the in-memory indices.
    Scales O(1) per injected prefix instead of O(N) thrift calls.
    """
    bgp = await driver.bgp()

    # --- 1. Bulk full-RIB dump (single call) ---
    # NOTE: use full RIB (getRibEntries) not shadow RIB. Locally-originated
    # routes on an STSW can be filtered by outbound policy before reaching
    # the shadow (advertise) RIB, even though they're committed to the local
    # RIB — shadow RIB would falsely report paths=0 for those prefixes.
    logger.info(f"[{driver.hostname}] Bulk getRibEntries (full RIB, both AFIs) ...")
    rib_entries = await bgp.async_get_bgp_rib_entries()
    logger.info(
        f"[{driver.hostname}] getRibEntries returned {len(rib_entries)} entries; "
        f"building index ..."
    )
    rib_index = _index_rib_entries(rib_entries)

    # --- 2. Bulk community-filtered RIB (single call) ---
    community_ids = [f"{c.asn}:{c.value}" for c in communities]
    logger.info(
        f"[{driver.hostname}] Bulk getRibEntriesForCommunities for "
        f"{len(community_ids)} communities ..."
    )
    comm_entries = await bgp.async_get_rib_entries_for_communities(
        TBgpAfi.AFI_IPV6, community_ids
    )
    logger.info(
        f"[{driver.hostname}] getRibEntriesForCommunities returned "
        f"{len(comm_entries)} entries; building index ..."
    )
    comm_prefix_set = {
        norm
        for entry in comm_entries
        if (norm := _normalize_prefix(_entry_prefix_str(entry))) is not None
    }

    # --- 3. Per-prefix lookup against indices (no more thrift calls) ---
    results: List[ValidationResult] = []
    for p in injected_prefixes:
        target_norm = _normalize_prefix(prefix_to_str(p))
        paths = rib_index.get(target_norm, 0) if target_norm else 0
        in_rib = target_norm is not None and target_norm in rib_index
        in_comm = target_norm is not None and target_norm in comm_prefix_set
        results.append(
            ValidationResult(
                rib_lookup_passed=in_rib,
                rib_lookup_paths=paths,
                community_lookup_passed=bool(comm_prefix_set),
                community_lookup_prefix_found=in_comm,
            )
        )
    return results


def print_report(
    device: str,
    prefix_strs: Sequence[str],
    communities: Sequence[str],
    results: Sequence[ValidationResult],
    out: TextIO = sys.stdout,
) -> bool:
    all_passed = all(
        r.rib_lookup_passed and r.community_lookup_prefix_found for r in results
    )
    print("\n" + "=" * 78, file=out)
    print(f"  BGP prefix injection report — {device}", file=out)
    print("=" * 78, file=out)
    print(f"  Communities:   {len(communities)} attached", file=out)
    print(f"    {', '.join(communities)}", file=out)
    print("-" * 78, file=out)
    print(f"  {'Prefix':<38} {'RIB by prefix':<16} {'RIB by community':<18}", file=out)
    print(f"  {'-' * 38} {'-' * 16} {'-' * 18}", file=out)
    for prefix_str, r in zip(prefix_strs, results):
        by_pref = (
            f"{'PASS' if r.rib_lookup_passed else 'FAIL'} (paths={r.rib_lookup_paths})"
        )
        by_comm = "PASS" if r.community_lookup_prefix_found else "FAIL"
        print(f"  {prefix_str:<38} {by_pref:<16} {by_comm:<18}", file=out)
    print("-" * 78, file=out)
    print(f"  OVERALL: {'PASS' if all_passed else 'FAIL'}", file=out)
    print("=" * 78 + "\n", file=out)
    return all_passed


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help=f"Single device hostname to inject into (default: {DEFAULT_DEVICE}). "
        "Ignored if --devices is set.",
    )
    parser.add_argument(
        "--devices",
        default=None,
        help="Comma-separated list of device hostnames to inject into. "
        "Each device gets the same prefixes/communities/flags in sequence. "
        "Example: --devices stsw001.s001.l202.mwg2,stsw001.s002.l202.mwg2,"
        "stsw001.s003.l202.mwg2",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Single CIDR prefix (default: {DEFAULT_PREFIX}). Ignored if "
        "--prefixes or --prefix-base+--count given.",
    )
    parser.add_argument(
        "--prefixes",
        default=None,
        help="Comma-separated list of CIDR prefixes (overrides --prefix). "
        "Example: '5000:dd::/64,5000:dd:1::/64,5000:dd:2::/64'",
    )
    parser.add_argument(
        "--prefix-base",
        default=None,
        help="Base CIDR to auto-generate a range of prefixes from. "
        "Used with --count and --increment-step. Overrides --prefix and --prefixes. "
        "Example: --prefix-base 5000:dd::/64 --count 16 --increment-step 0:0:1::  "
        "yields 5000:dd::, 5000:dd:1::, ... 5000:dd:f::/64",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of prefixes to generate from --prefix-base (default: 1)",
    )
    parser.add_argument(
        "--increment-step",
        default="0:0:1::",
        help="IPv6 address that indicates which hextet to advance each step "
        "(default: '0:0:1::' = increment 3rd hextet). "
        "Examples: '::1' = increment lowest hextet, "
        "'0:0:0:1::' = increment 4th hextet, "
        "'0:0:1:0:0:0:0:0' = same as '0:0:1::'.",
    )
    parser.add_argument(
        "--community-list",
        choices=sorted(COMMUNITY_PRESETS.keys()),
        default=None,
        help="Use a built-in preset community list (gtsw or stsw). "
        "Overrides --communities. 'gtsw' uses PATH_COMMUNITY_GTSW_*_HOP1 "
        "(65441:2241, 65441:2305); 'stsw' uses PATH_COMMUNITY_STSW_*_HOP2 "
        "(65441:2242, 65441:2306). The other 12 communities are identical "
        "across both presets.",
    )
    parser.add_argument(
        "--communities",
        default=",".join(GTSW_COMMUNITIES),
        help=(
            "Comma-separated list of 'ASN:VALUE' communities "
            "(default: the gtsw preset). Ignored if --community-list is set."
        ),
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Withdraw the prefix(es) via delNetworks() after validation",
    )
    parser.add_argument(
        "--withdraw",
        action="store_true",
        help="Withdraw-only mode: call delNetworks() and exit. Skips injection "
        "and validation.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip the RIB validation step (inject only)",
    )
    parser.add_argument(
        "--show-fsdb-communities",
        action="store_true",
        help="After injection, fetch FSDB bgp/ribMap and print the "
        "prefix -> community list for each injected prefix (validates the "
        "view that HRT actually subscribes to).",
    )
    parser.add_argument(
        "--fsdb-only-injected",
        action="store_true",
        help="When --show-fsdb-communities is set, restrict the output to "
        "the prefixes injected in this run (default: also includes any "
        "matching prefixes already in the ribMap).",
    )
    parser.add_argument(
        "--validate-hrt-host",
        default=None,
        help="GPU/BE-Node host running HRT (e.g., rtptest1544.mwg2). "
        "If set, after injection the script queries HRT getPrefixTable() "
        "and asserts each injected prefix is present ONLY on the lane "
        "corresponding to --device (gtsw00N -> plane N-1).",
    )
    parser.add_argument(
        "--validate-hrt-device-id",
        type=int,
        default=0,
        help="HRT device_id (GPU index) to filter the prefix table by "
        "(default: 0). The same lane assertion is applied within this device.",
    )
    parser.add_argument(
        "--validate-hrt-expected-plane",
        type=int,
        default=None,
        help="Override the expected plane (lane). Default is auto-derived "
        "from --device (gtsw00N -> plane N-1).",
    )
    return parser.parse_args()


GTSW_HOST_RE = re.compile(r"gtsw0*(\d+)\b", re.IGNORECASE)


def derive_plane_from_gtsw(gtsw_host: str) -> Optional[int]:
    """gtsw001 -> plane 0, gtsw002 -> plane 1, ... gtsw008 -> plane 7."""
    m = GTSW_HOST_RE.search(gtsw_host)
    if not m:
        return None
    n = int(m.group(1))
    if not 1 <= n <= 8:
        return None
    return n - 1


@dataclass
class HrtLaneCheck:
    prefix: str
    found: bool
    planes_present: List[int]
    expected_plane: int
    extra_planes: List[int]
    passed: bool


async def validate_hrt_lane_isolation(
    gpu_host: str,
    device_id: int,
    expected_plane: int,
    injected_prefix_strs: Sequence[str],
) -> List[HrtLaneCheck]:
    """Query HRT getPrefixTable() on `gpu_host` for `device_id` and assert
    that each injected prefix is present only on `expected_plane`.

    Returns a per-prefix result list.
    """
    logger.info(
        f"[{gpu_host}] Connecting to HRT (port 5909) for prefix-table check "
        f"on device {device_id}, expected plane {expected_plane} ..."
    )
    injected_norm = {
        str(ipaddress.ip_network(p, strict=False)) for p in injected_prefix_strs
    }
    client_ctx = await get_hrt_client(gpu_host)
    async with client_ctx as client:
        prefixes = await client.getPrefixTable()
    logger.info(f"[{gpu_host}] HRT getPrefixTable returned {len(prefixes)} entries")

    by_prefix: Dict[str, List[int]] = {}
    for entry in prefixes:
        if entry.device_id != device_id:
            continue
        try:
            norm = str(ipaddress.ip_network(entry.prefix, strict=False))
        except Exception:
            continue
        if norm not in injected_norm:
            continue
        planes = sorted({p.plane_id for p in (entry.planes or [])})
        by_prefix.setdefault(norm, []).extend(planes)

    checks: List[HrtLaneCheck] = []
    for raw in injected_prefix_strs:
        norm = str(ipaddress.ip_network(raw, strict=False))
        planes_present = sorted(set(by_prefix.get(norm, [])))
        found = bool(planes_present)
        extra = [p for p in planes_present if p != expected_plane]
        passed = found and (planes_present == [expected_plane])
        checks.append(
            HrtLaneCheck(
                prefix=raw,
                found=found,
                planes_present=planes_present,
                expected_plane=expected_plane,
                extra_planes=extra,
                passed=passed,
            )
        )
    return checks


def print_hrt_lane_report(
    gpu_host: str,
    device_id: int,
    checks: Sequence[HrtLaneCheck],
    out: TextIO = sys.stdout,
) -> bool:
    all_passed = all(c.passed for c in checks)
    print("\n" + "=" * 78, file=out)
    print(
        f"  HRT lane-isolation check  (host={gpu_host}, device_id={device_id})",
        file=out,
    )
    print("=" * 78, file=out)
    print(f"  {'Prefix':<38} {'Found':<6} {'Planes seen':<16} {'Result':<10}", file=out)
    print(f"  {'-' * 38} {'-' * 6} {'-' * 16} {'-' * 10}", file=out)
    for c in checks:
        result = "PASS" if c.passed else "FAIL"
        if not c.found:
            note = "(missing)"
        elif c.extra_planes:
            note = f"(extra={c.extra_planes})"
        else:
            note = ""
        print(
            f"  {c.prefix:<38} {('yes' if c.found else 'no'):<6} "
            f"{str(c.planes_present):<16} {result:<10} {note}",
            file=out,
        )
    print("-" * 78, file=out)
    print(
        f"  OVERALL: {'PASS' if all_passed else 'FAIL'}  "
        f"(expected plane={checks[0].expected_plane if checks else '?'} only)",
        file=out,
    )
    print("=" * 78 + "\n", file=out)
    return all_passed


async def show_fsdb_communities(
    driver: FbossSwitchInternal,
    injected_prefix_strs: Sequence[str],
    only_injected: bool,
    out: TextIO = sys.stdout,
) -> Dict[str, List[str]]:
    """Fetch FSDB bgp/ribMap and print prefix -> community list.

    Returns the printed map for callers that want to assert on it.
    Reuses neteng.test_infra.dne.taac.libs.fpf.fpf_fsdb_ribmap as a library.
    """
    logger.info(
        f"[{driver.hostname}] Fetching FSDB bgp/ribMap (getOperState) "
        f"to extract per-prefix communities ..."
    )
    rib_map = await get_fsdb_rib_map(driver)
    if not rib_map:
        print(
            f"\n  FSDB ribMap is empty or unavailable on {driver.hostname}.", file=out
        )
        return {}

    full_map = parse_rib_map_communities(rib_map)

    injected_norm = {
        str(ipaddress.ip_network(p, strict=False)) for p in injected_prefix_strs
    }

    def matches(prefix_str: str) -> bool:
        try:
            return str(ipaddress.ip_network(prefix_str, strict=False)) in injected_norm
        except Exception:
            return False

    if only_injected:
        filtered = {p: c for p, c in full_map.items() if matches(p)}
    else:
        filtered = full_map

    print("\n" + "=" * 78, file=out)
    print(f"  FSDB ribMap prefix -> communities  ({driver.hostname})", file=out)
    print(
        f"  ribMap entries: {len(full_map)}; shown: {len(filtered)}"
        f"{'  (injected only)' if only_injected else ''}",
        file=out,
    )
    print("=" * 78, file=out)
    if not filtered:
        print("  (no matching prefixes found in FSDB ribMap)", file=out)
    else:
        for prefix_str in sorted(filtered):
            comms = filtered[prefix_str]
            marker = "*" if matches(prefix_str) else " "
            comm_display = ", ".join(comms) if comms else "(none)"
            print(f"  {marker} {prefix_str:<40} {comm_display}", file=out)
        if not only_injected:
            print("\n  (* = prefix injected in this run)", file=out)
    print("=" * 78 + "\n", file=out)
    return filtered


def resolve_prefix_strs(args: argparse.Namespace) -> List[str]:
    """Pick the prefix source in priority order: --prefix-base > --prefixes > --prefix."""
    if args.prefix_base:
        return expand_prefix_range(args.prefix_base, args.count, args.increment_step)
    if args.prefixes:
        return [p.strip() for p in args.prefixes.split(",") if p.strip()]
    return [args.prefix]


def resolve_community_strs(args: argparse.Namespace) -> List[str]:
    """--community-list (preset) > --communities (explicit list)."""
    if args.community_list:
        return list(COMMUNITY_PRESETS[args.community_list])
    return [c.strip() for c in args.communities.split(",") if c.strip()]


def resolve_device_strs(args: argparse.Namespace) -> List[str]:
    """--devices (csv list) > --device (single)."""
    if args.devices:
        return [d.strip() for d in args.devices.split(",") if d.strip()]
    return [args.device]


async def run(args: argparse.Namespace) -> int:
    community_strs = resolve_community_strs(args)
    if not community_strs:
        logger.error("No communities provided")
        return 2
    if args.community_list:
        logger.info(
            f"Using preset community list '{args.community_list}' "
            f"({len(community_strs)} communities)"
        )

    prefix_strs = resolve_prefix_strs(args)
    if not prefix_strs:
        logger.error("No prefixes provided")
        return 2

    prefixes = [build_tip_prefix(p) for p in prefix_strs]
    communities = build_communities(community_strs)
    display_strs = [prefix_to_str(p) for p in prefixes]

    devices = resolve_device_strs(args)
    logger.info(
        f"Operating on {len(devices)} device(s) IN PARALLEL with "
        f"{len(prefixes)} prefix(es): {', '.join(devices)}"
    )

    # Per-device output buffers so async tasks don't interleave reports
    buffers: Dict[str, io.StringIO] = {d: io.StringIO() for d in devices}

    async def _one(device: str) -> bool:
        buf = buffers[device]
        print(f"\n{'#' * 78}\n#  DEVICE: {device}\n{'#' * 78}", file=buf)
        try:
            return await run_for_device(
                args,
                device,
                prefixes,
                communities,
                display_strs,
                community_strs,
                out=buf,
            )
        except Exception as e:
            print(f"\n  EXCEPTION on {device}: {e!r}\n", file=buf)
            logger.exception(f"[{device}] run_for_device failed")
            return False

    results_list = await asyncio.gather(*(_one(d) for d in devices))

    per_device_pass: Dict[str, bool] = dict(zip(devices, results_list))
    all_passed = all(results_list)

    await _flush_or_paste(
        devices=devices,
        prefix_count=len(prefixes),
        buffers=buffers,
        per_device_pass=per_device_pass,
        title=(
            "Multi-device WITHDRAW report"
            if args.withdraw
            else "Multi-device INJECT + VALIDATION report"
        ),
    )

    return 0 if all_passed else 1


# Threshold above which per-device reports are concatenated and uploaded to
# Everpaste rather than printed inline (avoids flooding the terminal for
# large injections / withdrawals).
INLINE_REPORT_PREFIX_THRESHOLD = 20


async def _flush_or_paste(
    devices: Sequence[str],
    prefix_count: int,
    buffers: Dict[str, io.StringIO],
    per_device_pass: Dict[str, bool],
    title: str,
) -> None:
    """If prefix_count is small, dump per-device buffers inline. Otherwise
    concatenate them all and upload to Everpaste; print only the link plus
    the multi-device summary inline."""
    big = prefix_count > INLINE_REPORT_PREFIX_THRESHOLD

    if not big:
        for d in devices:
            sys.stdout.write(buffers[d].getvalue())
        sys.stdout.flush()
    else:
        full = []
        full.append(f"{title}\n")
        full.append(f"Prefix count: {prefix_count}  |  Devices: {len(devices)}\n")
        full.append("=" * 78 + "\n\n")
        for d in devices:
            full.append(buffers[d].getvalue())
        body = "".join(full)
        try:
            ep_url = await async_everpaste_str(body, logger=logger)
            print(
                f"\n  Per-device report ({prefix_count} prefixes × "
                f"{len(devices)} devices) is large -> uploaded to Everpaste"
            )
            print(f"  -> {ep_url}\n")
        except Exception as e:
            logger.error(
                f"Everpaste upload failed ({e}); falling back to inline output"
            )
            for d in devices:
                sys.stdout.write(buffers[d].getvalue())
            sys.stdout.flush()

    # Multi-device summary is always inline; it's tiny and important.
    if len(devices) > 1:
        print("\n" + "=" * 78)
        print("  Multi-device summary")
        print("=" * 78)
        for d in devices:
            print(f"  {'PASS' if per_device_pass[d] else 'FAIL'}  {d}")
        print("=" * 78 + "\n")


async def run_for_device(
    args: argparse.Namespace,
    device: str,
    prefixes: Sequence[TIpPrefix],
    communities: Sequence[TBgpCommunity],
    display_strs: Sequence[str],
    community_strs: Sequence[str],
    out: TextIO = sys.stdout,
) -> bool:
    """Inject/withdraw/validate against one device. Returns True on success."""
    logger.info(f"Connecting to {device} via FbossSwitchInternal ...")
    driver = FbossSwitchInternal(hostname=device, logger=logger)

    if args.withdraw:
        await withdraw_prefixes(driver, list(prefixes))
        print(
            f"\nWithdrew {len(prefixes)} prefix(es) from {device}: "
            f"{', '.join(display_strs)}\n",
            file=out,
        )
        return True

    await inject_prefixes(driver, list(prefixes), communities)

    if args.no_validate:
        logger.info("Validation skipped (--no-validate)")
        if args.show_fsdb_communities:
            await show_fsdb_communities(
                driver, display_strs, args.fsdb_only_injected, out=out
            )
        if args.cleanup:
            await withdraw_prefixes(driver, list(prefixes))
        return True

    results = await validate_injection_bulk(driver, prefixes, communities)
    passed = print_report(
        device, list(display_strs), list(community_strs), results, out=out
    )

    if args.show_fsdb_communities:
        await show_fsdb_communities(
            driver, display_strs, args.fsdb_only_injected, out=out
        )

    hrt_passed = True
    if args.validate_hrt_host:
        expected_plane = args.validate_hrt_expected_plane
        if expected_plane is None:
            expected_plane = derive_plane_from_gtsw(device)
        if expected_plane is None:
            logger.error(
                f"Cannot derive expected plane from {device!r}; "
                f"pass --validate-hrt-expected-plane explicitly."
            )
            hrt_passed = False
        else:
            checks = await validate_hrt_lane_isolation(
                args.validate_hrt_host,
                args.validate_hrt_device_id,
                expected_plane,
                list(display_strs),
            )
            hrt_passed = print_hrt_lane_report(
                args.validate_hrt_host,
                args.validate_hrt_device_id,
                checks,
                out=out,
            )

    if args.cleanup:
        await withdraw_prefixes(driver, list(prefixes))

    return passed and hrt_passed


def main() -> None:
    args = parse_args()
    try:
        exit_code = asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
