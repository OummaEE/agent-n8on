# INSTALLER_SPEC

## Purpose
This document defines how the installer behavior for agent-n8On should work.

The installer is not a side detail. It is one of the core product promises.
If the installer is unreliable, the product promise is broken.

---

## 1. Installer goal
The installer should make local usage of the app possible with minimal user friction.

The target user is not expected to manually understand or install the full stack.

The installer must aim to automate:
- dependency detection,
- dependency installation,
- base configuration,
- post-install verification,
- failure reporting.

---

## 2. Product promise
The product promise is “one-click install” from the user’s point of view.

Internally, this does not mean that installation is simple. It means the complexity is absorbed by the product rather than dumped on the user.

---

## 3. Installer scope
### In scope
- detect whether required components are present,
- install missing components when possible,
- configure local runtime paths/settings,
- verify installed components,
- show clear success/failure status,
- write logs for debugging.

### Out of scope
- pretending install succeeded when verification failed,
- silently skipping critical failures,
- requiring the user to reverse-engineer what broke.

---

## 4. Required components
The exact set may evolve, but the installer flow must treat required runtime components explicitly.

Typical required components include:
- desktop app runtime,
- Node.js / npm if needed by the chosen install strategy,
- n8n,
- Ollama,
- selected local model(s),
- local config directories,
- logs directory,
- any helper runtime used by the app.

---

## 5. Installer phases
### Phase 1 — Environment detection
The installer should detect:
- operating system,
- architecture,
- write permissions,
- whether required runtimes already exist,
- whether required local ports/services are already in use,
- whether network access is available if downloads are needed.

### Phase 2 — Install plan
The installer should build a concrete plan:
- what is already present,
- what must be installed,
- what version is targeted,
- what order steps must run in.

### Phase 3 — Dependency installation
The installer should execute installation steps in the intended order.

### Phase 4 — Configuration
The installer should configure:
- app directories,
- environment/config values,
- service URLs where needed,
- model references,
- startup assumptions.

### Phase 5 — Verification
The installer must verify each critical component.

Examples:
- can the app start,
- is n8n reachable,
- is Ollama reachable,
- is the intended model available,
- are required directories writable.

### Phase 6 — Final status
The installer must report:
- success,
- partial success,
- failure,
- exact blocking issue if not successful.

---

## 6. Verification rules
Installation is not successful until verification passes.

### Minimum verification expectations
1. app files are present,
2. critical runtime dependencies are installed,
3. n8n can be started or reached,
4. Ollama can be started or reached,
5. intended model is installed or queued clearly,
6. logs/config directories are usable.

### Important rule
A step finishing without a crash is not enough. The installer must verify the result of the step.

---

## 7. Failure handling
The installer must classify failures where possible.

### Category A — Download failure
Examples:
- network unavailable,
- download interrupted,
- checksum mismatch.

### Category B — Runtime install failure
Examples:
- Node/npm failed,
- n8n install failed,
- Ollama install failed,
- package manager returned non-zero exit code.

### Category C — Permission failure
Examples:
- cannot write to required directory,
- cannot modify required config,
- admin-level restrictions.

### Category D — Verification failure
Examples:
- package installed but executable unavailable,
- service installed but not reachable,
- model expected but not present.

### Category E — Partial install state
Examples:
- some components installed,
- others missing,
- retry/resume needed.

---

## 8. Logging requirements
Installer logs are mandatory.

### Logs should include
- install timestamp,
- environment summary,
- install plan,
- each executed step,
- stdout/stderr or equivalent error output,
- verification results,
- final status.

### Minimum principle
If installation fails and the reason cannot be identified from logs, the installer is not good enough.

---

## 9. Resume/retry expectation
The installer should be designed so that partial progress is not wasted when possible.

Preferred behavior:
- detect already completed steps,
- avoid reinstalling working components unnecessarily,
- retry only failed or missing parts.

---

## 10. User communication requirements
The installer should communicate in plain language.

The user should be able to understand:
- what is being installed,
- what succeeded,
- what failed,
- what the product can do next,
- what the user must do manually, if anything.

---

## 11. Truthfulness rule
The installer must never claim full success if:
- n8n is not working,
- Ollama is not working,
- the required model is not available,
- the application cannot actually start.

Partial success must be labeled as partial success.

---

## 12. Core installer quality bar
A good installer for this product:
- reduces setup pain,
- verifies reality instead of trusting exit codes,
- records useful logs,
- makes recovery possible,
- protects the product promise of one-click setup.
