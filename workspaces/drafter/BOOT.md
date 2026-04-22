# Drafter — BOOT checklist

1. Verify vLLM is reachable at http://127.0.0.1:8002/v1/models.
2. Verify the served model_id matches `paul-voice-latest`.
3. Verify the checkpoint SHA on disk matches config/voice_pin.yaml voice_pin.checkpoint_sha (Phase 3 enforcement).
4. If any check fails: do not draft. Emit a hard-block Event and exit.

Phase 1 stub: boot checks are placeholders. Phase 3 DRAFT-01 implements them.
