# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

"""QoS class-of-service constants for TAAC.

`ClassOfService` is defined here as a plain Python `IntEnum` so the TAAC
`health_check.thrift` schema does not depend on the internal
`neteng/qosdb/Cos.thrift` (which is not open-sourced). The integer values mirror
the historical qosdb `ClassOfService` enum, so the i32 values stored in
`TxQueueInfo.cos_list` / `BufferUtilizationThreshold.active_cos_list` are
unchanged and remain wire-compatible.
"""

from enum import IntEnum


class ClassOfService(IntEnum):
    UNSPEC = 0
    BRONZE = 1
    SILVER = 2
    GOLD = 3
    ICP = 4
    NC = 5
