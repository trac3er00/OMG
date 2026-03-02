

## Open Problems (2026-03-01 00:41:43)
- Need explicit reintroduction of bare-done quality gate behavior inside `hooks/stop_dispatcher.py` before keeping single-stop-group architecture.
- Need end-to-end context-pressure contract: pressure estimator -> auto-handoff signal -> dispatcher/quality-runner advisory/skip behavior in both standalone and callable paths.
- Need reason propagation at every `record_stop_block()` call site to make Guard 5 discrimination meaningful.
