#!/usr/bin/env python3
"""End-to-end OSS smoke test against real FBOSS devices, via VP1.

Drives examples/live_smoke_config.py (a DummyStep + RunSSHCmdStep
playbook that runs `uname -a`) through the VP1 oss_entry_point CLI,
then prints the per-DUT `uname -a` output for visual confirmation
that the SSH step actually executed on each device.

Designed to run inside the `fboss-taac` derived image. The image
contains `taac/` but NOT `examples/`, so bind-mount the repo root
at `/taac` to expose this script and the topology CSVs:

    docker run --rm --network host \\
        -v "$PWD":/taac \\
        -e TAAC_OSS=1 -e TAAC_SSH_USER=<user> -e TAAC_SSH_PASSWORD=<pw> \\
        fboss-taac \\
        python3 /taac/examples/smoke_live_device.py \\
            --device-info-csv /taac/examples/topology/sample_device_info.csv \\
            --circuit-info-csv /taac/examples/topology/sample_circuit_info.csv

`--network host` is required so internal-DNS hostnames resolve from
inside the container. The image's entrypoint pre-exports PYTHONPATH /
LD_LIBRARY_PATH / TAAC_OSS, so no env wiring is needed at the caller.

Flag summary:
  --device-info-csv   REQUIRED. Sets TAAC_DEVICE_INFO_PATH so the OSS
                      topology loader picks up an environment-specific
                      fixture and `async_get_device_driver` can dispatch
                      to FbossSwitch via the per-host `operating_system`
                      column. Every hostname listed is used as a DUT,
                      unless --hosts narrows the set.
  --hosts             Optional. Subset of --device-info-csv's hosts.
  --circuit-info-csv  Sets TAAC_CIRCUIT_INFO_PATH for adjacency-aware tests.
                      Optional; DummyStep + RunSSHCmdStep don't need it.

Exits with oss_entry_point's exit code (0 on PASS, non-zero on failure).
"""

import argparse
import asyncio
import csv
import os
import sys


REQUIRED_ENV = ("TAAC_OSS", "TAAC_SSH_USER", "TAAC_SSH_PASSWORD")


def _read_hostnames_from_csv(path: str) -> list:
    """Return the hostname column from a device_info.csv, skipping comment/blank lines."""
    with open(path, newline="") as f:
        rows = (line for line in f if line.strip() and not line.startswith("#"))
        return [row[0] for row in csv.reader(rows) if row and row[0]]


def _preflight() -> None:
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        sys.exit(
            f"Missing required env vars: {', '.join(missing)}.\n"
            f"See the docstring at the top of this file for the full setup."
        )


async def _demo_ssh_output(hosts: list) -> None:
    """Re-run `uname -a` per DUT and print stdout.

    Strictly for visual confirmation that VP1's RunSSHCmdStep actually
    reached each device — it's not part of the VP1 test flow. The VP1
    pass/fail signal is already produced by oss_entry_point above.

    Uses AsyncSSHClient as an async context manager so each per-host
    connection is closed before moving to the next; otherwise a long
    DUT list builds up open sockets / asyncssh tasks until interpreter
    teardown (harmless on a tiny smoke, but a bad pattern to leave in
    an example).
    """
    from taac.utils.oss_driver_utils import AsyncSSHClient
    print("\n=== uname -a per DUT (visual confirmation) ===")
    for h in hosts:
        async with AsyncSSHClient(h) as cli:
            result = await cli.async_run("uname -a")
            print(f"--- {h} ---")
            print((result.stdout or "").rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--device-info-csv",
        required=True,
        help=(
            "Required path to a device_info.csv file. Sets "
            "TAAC_DEVICE_INFO_PATH so the OSS topology loader picks up "
            "your environment's device list (hostname -> OS / role / "
            "hardware) — the OS column is what async_get_device_driver "
            "dispatches on, so the smoke can't pick FbossSwitch (or any "
            "driver) without it. See examples/topology/ for a sample."
        ),
    )
    parser.add_argument(
        "--hosts",
        nargs="+",
        required=False,
        help=(
            "Optional subset of hostnames from --device-info-csv to "
            "smoke-test. If omitted, every hostname listed in the CSV "
            "is used as a DUT."
        ),
    )
    parser.add_argument(
        "--circuit-info-csv",
        default=None,
        help=(
            "Optional path to a circuit_info.csv file. Sets "
            "TAAC_CIRCUIT_INFO_PATH so the OSS topology loader picks up "
            "your environment's links. See examples/topology/ for a sample."
        ),
    )
    args = parser.parse_args()

    _preflight()

    # Set topology env vars BEFORE importing the runner so the
    # @memoize_forever-cached loaders land on the right paths.
    os.environ["TAAC_DEVICE_INFO_PATH"] = os.path.abspath(args.device_info_csv)
    if args.circuit_info_csv:
        os.environ["TAAC_CIRCUIT_INFO_PATH"] = os.path.abspath(args.circuit_info_csv)

    # Resolve hosts: full CSV, optionally narrowed by --hosts.
    csv_hosts = _read_hostnames_from_csv(args.device_info_csv)
    if args.hosts:
        unknown = [h for h in args.hosts if h not in csv_hosts]
        if unknown:
            parser.error(
                f"--hosts not present in --device-info-csv: {', '.join(unknown)}. "
                f"CSV contains: {', '.join(csv_hosts)}."
            )
        hosts = args.hosts
    else:
        hosts = csv_hosts

    # Drive VP1's oss_entry_point against the static test config.
    from taac.runner.oss_entry_point import main as oss_main
    config_path = os.path.join(os.path.dirname(__file__), "live_smoke_config.py")
    exit_code = oss_main([
        "--test-configs", config_path,
        "--dut", *hosts,
        "--skip-post-setup-wait",
    ])
    if exit_code != 0:
        return exit_code

    # Visual confirmation that the SSH step actually executed on each DUT.
    asyncio.run(_demo_ssh_output(hosts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
