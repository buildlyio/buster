---
id: ollama-diagnostic
name: Ollama diagnostic
description: Diagnose why the local Ollama server is unavailable and propose a safe fix.
tools:
  - system.check
  - network.check
context:
  - system
permissions:
  - system.read
---

1. Check whether Ollama is installed and whether the process is running.
2. Check whether port 11434 is reachable.
3. Look for a recent service error.
4. Explain the likely cause plainly.
5. If a restart would help, propose the "restart_ollama" action (risk level 2)
   and wait for explicit approval before executing.
