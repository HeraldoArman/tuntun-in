"""Tuntun.In AI Mobility Companion Agent package.

Dual-brain architecture (Reflex + Reasoning):

- Reflex Layer: Gemini Live (``agent.TuntunAgent``) — instant audio-visual
  obstacle detection + spatial warnings. Always on, low-latency, gated behind
  the "Hey Tutu" wake word for reactive conversation.

- Hazard Detection Loop (``hazard_loop``): a separate perception loop that
  samples the chest-camera frame and classifies hazards with a fast non-
  realtime Gemini model. This is the proactive trigger source that bypasses
  the wake gate and feeds the Priority Manager.

- Priority Manager (``priority``): the arbiter between the two trigger
  sources. Owns the IDLE / ACTIVE_CONVERSATION / SPEAKING state machine
  (driven by LiveKit agent_state_changed), a per-hazard cooldown, and the
  3-level CRITICAL / MODERATE / LOW interrupt policy. Hazards always preempt
  casual conversation; casual conversation never preempts a hazard.

- Reasoning Layer (``reasoning``): LangChain + DeepAgents, invoked on demand
  via the ``reroute_around_hazards`` function_tool. Queries the crowdsourced
  hazard map (Convex) and reasons about a landmark-grounded detour. Slow path,
  never safety-critical.

- Deep Navigator (``navigator``): Google Maps helpers + macro-to-micro
  landmark guidance, called via the ``navigate_to`` function_tool. Uses the
  return-fast + background-task + generate_reply pattern to avoid dead-air.

Wake word gating ("Hey Tutu"): the agent only listens to the user after the
wake word is detected (openwakeword ONNX model, ``wakeword`` module). Manual
turn detection means proactive warnings come from the hazard loop, not the
wake word path.

Modules:
- logging_setup: logging config + startup env banner
- convex: Convex DB connectivity (best-effort)
- navigator: Deep Navigator Google Maps helpers + macro-to-micro guidance
- events: verbose LiveKit room/session event loggers + GPS/profile data handlers
- wakeword: "Hey Tutu" wake word detector (openwakeword + ONNX)
- priority: Priority Manager + agent state machine
- hazard_loop: separate hazard detection loop (feeds Priority Manager)
- reasoning: LangChain/DeepAgents reasoning layer (detour around hazards)
- crowdsource: silent crowdsourced hazard reporting
- overwatch: emergency spectator mode + WhatsApp guardian alert
- agent: TuntunAgent (Reflex Layer) + navigate_to / trigger_overwatch /
  report_road_hazard / reroute_around_hazards tools
"""
