"""Tuntun.In AI Mobility Companion Agent package.

Dual-brain architecture:
- Reflex Layer: Gemini Live (instant audio-visual obstacle detection)
- Reasoning Layer: LangChain DeepAgents (multi-step route orchestration)

Modules:
- logging_setup: logging config + startup env banner
- convex: Convex DB connectivity (best-effort)
- navigator: Deep Navigator Google Maps helpers + macro-to-micro guidance
- events: verbose LiveKit room/session event loggers + GPS data handler
- agent: TuntunAgent (Reflex Layer) + navigate_to tool
"""
