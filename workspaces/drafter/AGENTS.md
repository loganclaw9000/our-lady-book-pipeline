# Drafter — Operating Instructions (Phase 1 stub)

Phase 1 status: stub. The drafter loop is built in Phase 3 (DRAFT-01, DRAFT-02).

When Phase 3 lands, this file will specify:
- Input: SceneRequest + ContextPack (bundled by the RAG bundler — Phase 2).
- Output: DraftResponse written to drafts/scene_buffer/<chapter>/<scene>.draft.json.
- Model: vllm/paul-voice-latest (pinned in config/voice_pin.yaml, SHA-verified on boot).
- EventLogger emission: every draft call emits an Event with role='drafter', mode='A',
  checkpoint_sha=<pin sha>, tokens, latency, output_sha.

For now: do not invoke this agent.
