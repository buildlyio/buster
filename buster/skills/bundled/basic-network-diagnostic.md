---
id: basic-network-diagnostic
name: Basic network diagnostic
description: Run read-only network checks and explain connectivity problems.
tools:
  - network.check
  - network.resolve_dns
context:
  - system
permissions:
  - system.read
---

1. Run the network health checks.
2. Identify the first failing layer (interface, gateway, DNS, internet).
3. Explain the problem plainly and note that local features still work offline.
4. Do not run aggressive scans. Any broader scan requires explicit approval and
   a stated scope.
