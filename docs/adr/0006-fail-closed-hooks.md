# Hook chain is fail-closed

A Hook that raises an unhandled exception is treated as a deny verdict. The tool call is blocked, the exception is logged, and the Agent Session receives an error it can adapt to.

The alternative — fail-open (exception → allow) — was rejected as the default because the failure mode is more dangerous: a broken Hook that was meant to block a destructive command silently permits it. Fail-open is available as a per-hook opt-in (`fail_open = true` in configuration) for Hook development and debugging only.
