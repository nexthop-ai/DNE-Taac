// Stub for QoS Class of Service definitions
namespace py neteng.qosdb.cos
namespace py3 neteng.qosdb
namespace cpp2 neteng.qosdb

// Class of Service enum - minimal stub for OSS build
enum ClassOfService {
  BE = 0,      // Best Effort
  AF1 = 1,     // Assured Forwarding 1
  AF2 = 2,     // Assured Forwarding 2
  AF3 = 3,     // Assured Forwarding 3
  AF4 = 4,     // Assured Forwarding 4
  EF = 5,      // Expedited Forwarding
  CS6 = 6,     // Class Selector 6
  CS7 = 7,     // Class Selector 7
  NC = 8,      // Network Control
  // Meta-specific QoS classes for internal traffic management
  BRONZE = 9,  // Bronze tier
  SILVER = 10, // Silver tier
  GOLD = 11,   // Gold tier
  ICP = 12,    // Inter-Cluster Protocol
}
