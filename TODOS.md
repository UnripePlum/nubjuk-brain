# TODOS

## Brain P1 Mock Strict Binary Validation Follow-up

What: After the first MCU happy-path pass succeeds, decide whether binary-frame warnings should become strict `schema_invalid` errors.

Why: The P1 mock brain currently logs sequence mismatch, non-zero reserved byte, and unusual PCM payload size as warnings while still returning `intent=roll_right`. That is useful for first hardware bring-up, but too forgiving after the MCU encoder is known to work.

Pros:
- Catches MCU audio-frame encoder bugs earlier.
- Keeps first bring-up forgiving while preserving the stricter protocol decision.
- Gives the later Phase 4 brain a cleaner contract baseline.

Cons:
- Adds one follow-up decision after hardware verification.
- Requires stricter WebSocket tests once enabled.
- Could make early hardware debugging noisier if enabled too soon.

Context: The approved MCU Happy Path Mock Brain design intentionally warns instead of failing on binary-frame anomalies. Revisit this after the flow `session_start -> audio frames -> session_end -> intent=roll_right` succeeds on real ESP32-S3 hardware.

Depends on / blocked by: First successful MCU happy-path verification using the mock brain.
