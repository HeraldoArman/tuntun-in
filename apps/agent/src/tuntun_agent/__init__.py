"""Tuntun.In AI Mobility Companion Agent package.

Single-brain Reflex architecture:
- Reflex Layer: Gemini Live (instant audio-visual obstacle detection +
  navigation via Google Maps direct API calls).

A LangChain DeepAgents reasoning layer is a planned future addition for
multi-step route orchestration, but is NOT implemented yet. The navigator
module currently calls the Google Maps API directly via httpx — no LangChain
dependency is used at runtime, even though `deepagents` is in pyproject.toml
for forward compatibility.

Wake word gating ("Hey Tutu"): the agent only listens to the user after the
"Hey Tutu" wake word is detected (openwakeword ONNX model). See the wakeword
module.

Modules:
- logging_setup: logging config + startup env banner
- convex: Convex DB connectivity (best-effort)
- navigator: Deep Navigator Google Maps helpers + macro-to-micro guidance
- events: verbose LiveKit room/session event loggers + GPS data handler
- wakeword: "Hey Tutu" wake word detector (openwakeword + ONNX)
- agent: TuntunAgent (Reflex Layer) + navigate_to tool
"""
