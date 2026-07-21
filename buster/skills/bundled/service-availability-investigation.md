---
id: service-availability-investigation
name: Service availability investigation
description: Investigate why a discovered local service or Buster node is unavailable.
tools:
  - discovery.list
  - discovery.scan
  - network.resolve_dns
context:
  - system
permissions:
  - network
---

1. List discovered services and nodes with their trust status.
2. Re-probe the target's LCDP manifest (read-only).
3. Check name resolution and reachability for the target host.
4. Report whether the service is unreachable, unhealthy, or simply not trusted.
5. Never connect to or trust a service automatically — surface the decision to
   the user.
