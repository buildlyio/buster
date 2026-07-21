---
id: system-health-check
name: System health check
description: Run read-only system checks and explain any problems in plain language.
tools:
  - system.check
  - system.processes
context:
  - system
permissions:
  - system.read
---

1. Run the system health checks.
2. For each warning or critical result, explain the problem plainly.
3. Distinguish observation from interpretation.
4. Recommend safe next steps, but do not perform system-changing actions
   without explicit approval.
