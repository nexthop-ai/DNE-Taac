/*
 * Minimal stub for bgp_policy.thrift
 * This is a minimal OSS version for TAAC compilation
 */

namespace py3 configerator.structs.neteng.bgp_policy.thrift

enum DIRECTION {
  IN = 0,
  OUT = 1,
}

enum DrainState {
  UNDRAINED = 0,
  DRAINED = 1,
  DRAINING = 2,
}

struct BgpPolicy {
  1: string name;
  2: i32 priority;
}

struct BgpPolicies {
  1: list<BgpPolicy> policies;
}
