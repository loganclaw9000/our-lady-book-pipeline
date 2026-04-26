"""Physics pre-flight gate base re-exports (Plan 07-01).

Plan 07-03 will land per-gate files (pov_lock, motivation, ownership, treatment,
quantity) and the run_pre_flight composer.
"""

from book_pipeline.physics.gates.base import GateError, GateResult, emit_gate_event

__all__ = ["GateError", "GateResult", "emit_gate_event"]
