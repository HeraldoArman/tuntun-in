# Tuntun.In

A mobility companion for visually impaired pedestrians in Indonesia. A
chest-mounted phone streams live camera + mic to a LiveKit room; a Python
agent watches the feed, warns about street hazards with spatial audio,
guides navigation, silently maps damaged infrastructure for other blind
users, and escalates life-threatening danger to a linked guardian over
WhatsApp with a live camera feed.

Built with Next.js + LiveKit + Gemini Live + Convex + Better-T-Auth.

## Features

1. **Reflex AI — real-time vision-to-audio** (core): the Reflex Layer (Gemini
   Live) watches the chest-camera feed and speaks instant spatial warnings for
   Indonesian street obstacles — parked motorcycles on sidewalks, open
   manholes, potholes, drainage gutters, low banners, excavation pits.
2. **Deep Navigator — macro-to-micro navigation** (core): the `navigate_to`
   tool fetches a walking route from Google Maps, then the Reflex Layer grounds
   each maneuver in what the camera actually shows ("turn left just past the
   blue food cart" instead of "turn left in 50 meters"). Uses a return-fast +
   background-task + follow-up reply pattern so the user never hears dead air
   while the route is being fetched.
3. **Overwatch Mode — emergency spectator** (core): when the agent detects
   critical, life-threatening danger (a fall, stepping into an excavation pit,
   an imminent collision), it mints a one-shot LiveKit spectator token, opens
   a public `/spectator` WebRTC page, and texts the link to the user's linked
   guardian over WhatsApp (via GoWA). The guardian sees the live camera and
   guides the user verbally.
4. **Live Crowdsourced Mapping** (core): the `report_road_hazard` tool
   silently snapshots the camera + GPS and stores damaged-infrastructure
   reports (image + coordinates + description) in Convex. No spoken
   confirmation — the user is never interrupted. A public `/map` dashboard
   renders every report so other blind users can avoid known bad road/sidewalk.
5. **Transit Spotter — contextual OCR** (optional, not implemented).

## Architecture — dual brain

The agent is split into two layers, mirroring the human nervous system: a
fast always-on reflex (spinal cord) and a slow on-demand reasoner (cortex).

```mermaid
flowchart LR
    Client["<b>Next.js client</b><br/>(apps/web)<br/>cam, mic, GPS, data"]

    subgraph Agent["Python LiveKit Agent (apps/agent)"]
        direction TB
        Reflex["<b>Reflex Layer</b> (Gemini Live)<br/>• wake-word gated conversation<br/>• navigate_to / trigger_overwatch /<br/>  report_road_hazard / reroute_..."]
        Hazard["<b>Hazard Detection Loop</b> (gemini-flash)<br/>• samples chest frame every ~1.5s<br/>• classifies hazards → Priority Manager"]
        Priority["<b>Priority Manager</b> (state machine)<br/>• IDLE / ACTIVE_CONVERSATION / SPEAKING<br/>• 3-level CRITICAL / MODERATE / LOW<br/>• per-hazard cooldown"]
        Reasoning["<b>Reasoning Layer</b> (LangChain + DeepAgents)<br/>• reroute_around_hazards tool<br/>• queries crowdsourced hazard map"]
        Reflex --> Priority
        Hazard --> Priority
        Reflex -. on-demand .-> Reasoning
    end

    GMaps["Google Maps"]
    Convex[("Convex<br/>hazards, overwatch,<br/>profiles, guardian links")]

    Client -->|"video + audio"| Agent
    Agent -->|"spatial audio"| Client
    Agent -.-> GMaps
    Agent <--> Convex
```

**Two trigger sources, one output channel.** Reactive conversation opens via
the "Hey Tutu" wake word (`turn_detection="manual"` — the agent ignores
ambient speech). Proactive hazard warnings come from the separate Hazard
Detection Loop and bypass the wake gate entirely. Both converge on one audio
output, so the **Priority Manager** arbitrates:

| Priority | Behavior |
|---|---|
| CRITICAL | `interrupt()` + speak warning immediately — always preempts any speech or conversation. |
| MODERATE | Wait for the current speech to finish, then interrupt + speak. |
| LOW | Speak only if the agent is idle; otherwise skip (not time-critical). |

Each hazard is keyed by description with a 5-second cooldown, so the same
hazard is not repeated while different hazards can still stack.

**Why split reflex from reasoning.** Putting perception and multi-step
reasoning in one model makes every response slow and expensive — but hazard
warnings need sub-second reaction. The Reflex Layer (Gemini Live) stays fast
and always on; the Reasoning Layer (LangChain + DeepAgents) is invoked only
on demand via a `function_tool` for the one case that needs real thinking —
finding a safer route that avoids known crowdsourced hazards. It is allowed to
take a few seconds and is never on the safety-critical hot path.

## Repo layout

```
apps/
  web/      Next.js client — Reflex call, public hazard map, spectator, dashboard
  agent/    Python LiveKit agent (the dual-brain above)
  gowa/     go-whatsapp-web-multidevice (WhatsApp delivery for Overwatch)
packages/
  backend/  Convex schema + queries/mutations (hazards, overwatch, profiles, auth)
  ui/       Shared shadcn/ui primitives
  config, env
```

## Agent modules (`apps/agent/src/tuntun_agent`)

- `agent.py` — `TuntunAgent` (Reflex Layer) + the four `function_tool`s.
- `wakeword.py` — "Hey Tutu" openwakeword ONNX detector; reactive conversation only.
- `hazard_loop.py` — separate perception loop; classifies frames → Priority Manager.
- `priority.py` — state machine + 3-level interrupt policy + per-hazard cooldown.
- `navigator.py` — Google Maps geocode/directions + landmark-grounded guidance.
- `reasoning.py` — LangChain/DeepAgents detour reasoning (queries `hazardAgent:listNearby`).
- `crowdsource.py` — silent hazard report (frame → JPEG → Convex file storage → row).
- `overwatch.py` — spectator token + URL + Convex session + WhatsApp alert.
- `events.py` — verbose LiveKit event logging + GPS/profile data-channel handlers + frame buffer.
- `convex.py`, `logging_setup.py` — shared helpers.

## Convex schema (`packages/backend/convex/schema.ts`)

Four tables matching the demoed features: `userProfiles`, `guardianLinks`,
`hazardReports` (crowdsourced map), `overwatchSessions` (SOS). Agent-facing
mutations/queries (`hazardAgent:*`, `overwatchAgent:*`, `agent:*`) are gated
by `CONVEX_SERVICE_SECRET` — the agent has no user session. `hazard:listReports`
is public (the `/map` dashboard); `hazardAgent:listNearby` powers the detour
reasoning layer.

## Getting started

Install dependencies:

```bash
pnpm install
```

Convex setup:

```bash
pnpm run dev:setup
```

Follow the prompts to create a Convex project, then copy env from
`packages/backend/.env.local` into `apps/*/.env`. The Python agent reads its
own env from `apps/agent/.env` (see `apps/agent/.env.example`):
`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `GOOGLE_API_KEY`,
`GOOGLE_MAPS_API_KEY`, `CONVEX_URL`, `CONVEX_SERVICE_SECRET`,
`PUBLIC_WEB_URL`, and the `GOWA_*` vars for Overwatch WhatsApp delivery.

Run everything:

```bash
pnpm run dev          # web + convex + agent
pnpm run dev:web      # web only
pnpm run dev:agent    # python agent only
```

Web app: [http://localhost:3001](http://localhost:3001).

## Quality

- Python agent: `cd apps/agent && .venv/bin/ruff check src/`
- TypeScript / formatting: `pnpm dlx ultracite fix` (Biome), `pnpm run check-types`
- Convex typecheck: `cd packages/backend && pnpm convex codegen`

## Deployment

- **Docker Compose** — `pnpm run docker:build` / `docker:up` / `docker:logs`
  / `docker:down`. Config in `docker-compose.yml`; app Dockerfiles in
  `apps/*/Dockerfile`. Env read from each app's `.env`, overridden for
  container networking in `docker-compose.yml`.
- **Railway** — `apps/web`, `apps/agent`, and `apps/gowa` each ship a
  `railway.json`; the agent and web auto-deploy from their GitHub service
  source. See `.claude` memory notes for the wiring.

## UI customization

Shared shadcn/ui primitives live in `packages/ui`. Change design tokens in
`packages/ui/src/styles/globals.css`, primitives in
`packages/ui/src/components/*`, aliases in `packages/ui/components.json` and
`apps/web/components.json`. Add shared primitives:

```bash
npx shadcn@latest add accordion dialog popover -c packages/ui
```

Import: `import { Button } from "@tuntun-in/ui/components/button";`

## Available scripts

- `pnpm run dev` — start all apps in dev mode
- `pnpm run build` — build all apps
- `pnpm run dev:web` / `dev:agent` / `dev:server` — start one app
- `pnpm run dev:setup` — set up + connect Convex
- `pnpm run check-types` — TypeScript across all apps
- `pnpm run docker:build` / `docker:up` / `docker:logs` / `docker:down`
