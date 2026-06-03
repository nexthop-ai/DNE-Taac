/*
 * Minimal stub for vip_service_config.thrift
 * This is a minimal OSS version for TAAC compilation
 */

namespace py3 configerator.structs.neteng.config

struct VipServiceConfig {
  1: string name;
  2: string address;
  3: i32 port;
}
