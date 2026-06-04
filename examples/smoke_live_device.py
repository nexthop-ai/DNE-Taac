#!/usr/bin/env python3
"""End-to-end OSS smoke test against one or more real FBOSS devices.

Constructs a minimal TestConfig with a DummyStep playbook and a
RunSSHCmdStep playbook, points it at the host(s) supplied on the
command line, and drives it through TaacRunner under TAAC_OSS=1.

Designed to run *inside* a build container produced by
docker/run-fboss-docker.sh — there is no bare-metal path. Invoke via:

    ./docker/run-fboss-docker.sh --distro centos --network host run bash -c '
        export TAAC_OSS=1 TAAC_SSH_USER=<user> TAAC_SSH_PASSWORD=<pw>
        python3 -m pip install --break-system-packages --no-index \\
            --find-links /scratch/installed/fbthrift-python/share/thrift/wheels thrift > /dev/null
        python3 -m pip install --break-system-packages -r /taac/requirements.txt > /dev/null
        export PYTHONPATH=/taac:/scratch/installed/taac-<HASH>/lib/python3/site-packages
        export LD_LIBRARY_PATH=$(find /scratch/installed -maxdepth 2 -type d -name lib | tr "\\n" ":")
        python3 /taac/examples/smoke_live_device.py \\
            --device-info-csv /taac/examples/topology/sample_device_info.csv \\
            --circuit-info-csv /taac/examples/topology/sample_circuit_info.csv \\
            --command "uname -a"
    '

(Substitute <HASH> with the actual taac install-dir hash from
 `ls /scratch/installed/`. `--network host` is required so internal-DNS
 hostnames resolve from inside the container.)

Flag summary:
  --hosts             Optional. Subset of CSV hosts (or required if no CSV).
  --device-info-csv   Sets TAAC_DEVICE_INFO_PATH so the OSS topology loader
                      picks up an environment-specific fixture. If omitted,
                      every hostname in the CSV is used as a DUT.
  --circuit-info-csv  Sets TAAC_CIRCUIT_INFO_PATH for adjacency-aware tests.
                      Optional; DummyStep + RunSSHCmdStep don't need it.
  --command           Shell command to run via RunSSHCmdStep (default: hostname).

Exits 0 on success, 1 on failure (any step raising or the runner
returning an exception).
"""

import argparse
import asyncio
import csv
import json
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


async def _smoke(hosts: list, command: str, resolve_os_from_csv: bool) -> None:
    # Imports happen after the env-var preflight so the OSS gates take
    # the right branch at import time.
    from taac.test_as_a_config.thrift_types import (
        DeviceOsType,
        Endpoint,
        Params,
        Playbook,
        Stage,
        Step,
        StepName,
        TestConfig,
    )
    from taac.libs.taac_runner import TaacRunner

    # When the device_info CSV is provided, leave host_os_type_map empty
    # so async_get_device_driver falls through to the OSS topology
    # loader (which honors per-host OS from the CSV). Hardcoding FBOSS
    # here would otherwise shadow the CSV for any host you list, even
    # if the CSV says ARISTA / CISCO / etc.
    if resolve_os_from_csv:
        host_os_type_map = {}
    else:
        host_os_type_map = {h: DeviceOsType.FBOSS for h in hosts}

    cfg = TestConfig(
        name="live_smoke",
        basset_pool="",
        playbooks=[
            Playbook(
                name="dummy_playbook",
                stages=[Stage(steps=[Step(name=StepName.DUMMY_STEP)])],
            ),
            Playbook(
                name="ssh_playbook",
                stages=[
                    Stage(
                        steps=[
                            Step(
                                name=StepName.RUN_SSH_COMMAND_STEP,
                                step_params=Params(
                                    json_params=json.dumps(
                                        {"cmd": command, "log_output": True}
                                    )
                                ),
                            )
                        ]
                    )
                ],
            ),
        ],
        endpoints=[Endpoint(name=h, dut=True) for h in hosts],
        host_os_type_map=host_os_type_map,
        startup_checks=[],
    )
    runner = TaacRunner(test_config=cfg, skip_post_setup_wait=True)
    print(f"duts: {runner.duts}")
    await runner.async_test_setUp()
    await runner.run_tests()

    # Surface the actual SSH command output per device so the demo shows what
    # came back (the runner's RunSSHCmdStep logs it under log_output=True but
    # buries it under runner formatting; this is the explicit version).
    from taac.utils.oss_driver_utils import AsyncSSHClient
    print()
    print(f"=== output of `{command}` per DUT ===")
    for h in hosts:
        cli = AsyncSSHClient(h)
        result = await cli.async_run(command)
        print(f"--- {h} ---")
        print((result.stdout or "").rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--hosts",
        nargs="+",
        required=False,
        help=(
            "One or more device hostnames to smoke-test. If omitted, every "
            "hostname listed in --device-info-csv is used. Required if "
            "--device-info-csv is not given."
        ),
    )
    parser.add_argument(
        "--command",
        default="hostname",
        help="Shell command to run via RunSSHCmdStep (default: hostname).",
    )
    parser.add_argument(
        "--device-info-csv",
        default=None,
        help=(
            "Optional path to a device_info.csv file. Sets "
            "TAAC_DEVICE_INFO_PATH so the OSS topology loader picks up "
            "your environment's device list (hostname -> OS / role / "
            "hardware). See examples/topology/ for a sample."
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

    if not args.hosts and not args.device_info_csv:
        parser.error(
            "Provide --hosts, --device-info-csv, or both. "
            "(With --device-info-csv alone, every hostname in the CSV is used.)"
        )

    _preflight()

    # Set the topology env vars BEFORE importing the runner / loader, so
    # the @memoize_forever-cached load_device_info / load_circuit_info
    # calls land on the right CSV paths.
    if args.device_info_csv:
        os.environ["TAAC_DEVICE_INFO_PATH"] = os.path.abspath(args.device_info_csv)
    if args.circuit_info_csv:
        os.environ["TAAC_CIRCUIT_INFO_PATH"] = os.path.abspath(args.circuit_info_csv)

    if args.device_info_csv:
        csv_hosts = _read_hostnames_from_csv(args.device_info_csv)
        if not args.hosts:
            hosts = csv_hosts
        else:
            unknown = [h for h in args.hosts if h not in csv_hosts]
            if unknown:
                parser.error(
                    f"--hosts not present in --device-info-csv: {', '.join(unknown)}. "
                    f"CSV contains: {', '.join(csv_hosts)}."
                )
            hosts = args.hosts
        resolve_os_from_csv = True
    else:
        hosts = args.hosts
        resolve_os_from_csv = False

    try:
        asyncio.run(_smoke(hosts, args.command, resolve_os_from_csv))
    except Exception as exc:
        print(f"\nSMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("\nSMOKE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
