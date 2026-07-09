"""AWA consumer of the intent-router (phase A0).

This package is AWA-as-first-consumer of the shared intent-router: it authors AWA's
`intent-catalog/v1`, translates router proposals into plain language, and runs the thin
operator loop (hear -> map -> confirm-consequence -> AWA verb -> verify -> narrate ->
record-feedback). It NEVER executes a verb from the router's output — the router proposes,
AWA's own verbs execute, and the KERNEL (not the router) sources every consequence
confirmation.

Kernel-first / router-off: nothing in this package is on the kernel safety path, and every
module here degrades safely when the router is not installed (the loop asks; it never guesses
a destructive action). See `operator_loop.py`.
"""
