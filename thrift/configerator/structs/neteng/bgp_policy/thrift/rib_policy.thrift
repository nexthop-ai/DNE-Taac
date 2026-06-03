/*
 * Minimal stub for rib_policy.thrift
 * This is a minimal OSS version for TAAC compilation
 */

namespace py3 configerator.structs.neteng.bgp_policy.thrift

struct TPathSelector {
  1: string name;
}

struct TRouteAttributeUcmpAction {
  1: string action;
}

struct TRouteFilterPolicy {
  1: string name;
  2: i32 priority;
}

struct TRouteAttributePolicy {
  1: string name;
}

struct TPathSelectionPolicy {
  1: string name;
}

struct TRibPolicy {
  1: string name;
  2: i32 priority;
}
