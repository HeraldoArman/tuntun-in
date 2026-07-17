# 🦾 Tuntun.In

> **A mobility companion that gives a chest-mounted phone the eyes and voice
> of a trusted guide** — for visually impaired pedestrians in Indonesia.

A smartphone worn on the chest streams its live camera and microphone to a
cloud AI "agent" that watches the road, speaks instant spatial warnings
about Indonesian street hazards (parked motorcycles, open manholes,
potholes, drainage gutters), guides navigation, silently maps damaged
infrastructure for other blind users, and — when danger turns
life-threatening — escalates a live camera feed to a linked guardian over
WhatsApp.

Built with **Next.js · LiveKit · Gemini Live · Convex · Better-Auth**.

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
    %% ───────── INPUT ─────────
    Phone["📱 Chest-mounted phone<br/>camera · mic · GPS"]:::phone

    %% ───────── TRANSPORT ─────────
    subgraph LK["☁️ LiveKit Cloud — WebRTC"]
        direction TB
        RTC["real-time video + audio<br/>transport layer"]:::transport
    end

    Phone ==>|"🎥 + 🎙️ live stream"| RTC

    %% ───────── THE BRAIN ─────────
    subgraph Agent["🧠 Tuntun Agent — the dual brain (apps/agent, Python)"]
        direction TB

        subgraph Reflex["⚡ Reflex Layer — fast, always-on"]
            Wake["👂 'Hey Tutu' wake word<br/>openwakeword gate"]:::reflex
            Gemini["Gemini Live<br/>sees + speaks · conversational<br/>guidance & navigation"]:::reflex
            Wake --> Gemini
        end

        subgraph Eyes["👁️ Hazard Detection Loop"]
            Frame["samples chest frame<br/>every ~1.5 s"]:::eyes
            Classify["Gemini Flash<br/>classifies street hazards"]:::eyes
            Frame --> Classify
        end

        Priority["⚖️ Priority Manager<br/>state machine + cooldown<br/>arbitrates ALL spoken output"]:::priority

        subgraph Think["🧭 Reasoning Layer — slow, on-demand"]
            Deep["LangChain + DeepAgents<br/>hazard-aware rerouting"]:::think
        end

        Gemini --> Priority
        Classify --> Priority
        Gemini -.->|"on-demand<br/>function_tool"| Deep
        Deep -.->|"safer route"| Gemini
    end

    RTC -->|"stream in"| Reflex
    RTC -->|"stream in"| Eyes

    %% ───────── EXTERNAL SERVICES ─────────
    GMaps["🗺️ Google Maps<br/>walking directions"]:::svc
    Convex[("🗄️ Convex<br/>hazard reports · overwatch<br/>user + guardian profiles")]:::svc
    GoWA["💬 GoWA<br/>WhatsApp gateway"]:::svc

    %% ───────── OUTPUTS ─────────
    Audio["🔊 Spoken spatial audio<br/>→ phone speaker"]:::audio
    Map["📍 Public /map<br/>crowdsourced hazards"]:::mapOut
    SOS["🚨 Overwatch SOS<br/>live link → guardian"]:::sosOut

    Priority ==>|"interrupt + speak"| Audio
    Audio -.-> RTC
    RTC -.-> Phone

    Gemini -.->|"report_road_hazard<br/>(silent)"| Convex
    Deep -.->|"query nearby<br/>hazards"| Convex
    Gemini -.->|"navigate_to"| GMaps
    GMaps -.->|"route + maneuvers"| Gemini
    Priority -.->|"critical<br/>danger"| SOS
    SOS -.->|"spectator token"| Convex
    SOS -.->|"WhatsApp alert"| GoWA
    Convex -.->|"hazard data"| Map

    %% ───────── STYLES (blue-dominant palette, warm accents for SOS) ─────────
    classDef phone fill:#fff7ed,stroke:#f97316,stroke-width:2px,color:#7c2d12;
    classDef transport fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#075985;
    classDef reflex fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a;
    classDef eyes fill:#cffafe,stroke:#0891b2,stroke-width:2px,color:#155e75;
    classDef priority fill:#e0e7ff,stroke:#4f46e5,stroke-width:3px,color:#312e81;
    classDef think fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#4c1d95;
    classDef svc fill:#f1f5f9,stroke:#475569,stroke-width:2px,color:#1e293b;
    classDef audio fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a;
    classDef mapOut fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d;
    classDef sosOut fill:#fee2e2,stroke:#dc2626,stroke-width:3px,color:#7f1d1d;
```

#### Color legend

| Color | Role |
|---|---|
| 🟧 amber | The user's phone — physical input (camera, mic, GPS) |
| 🟦 light blue | LiveKit Cloud — WebRTC video + audio transport |
| 🔵 blue | **Reflex Layer** — fast, always-on vision + voice (Gemini Live) |
| 🩵 cyan | **Hazard Detection Loop** — continuous perception (Gemini Flash) |
| 🟣 indigo (thick) | **Priority Manager** — arbitrates *all* spoken output |
| 🟪 violet | **Reasoning Layer** — slow, on-demand route planning (DeepAgents) |
| ⬜ slate | External services (Google Maps, Convex, WhatsApp gateway) |
| 🟩 green | Crowdsourced public `/map` — hazard data for other blind users |
| 🟥 red (thick) | **Overwatch SOS** — live-camera escalation to a guardian |

> **Arrow types:** solid `→` = live media stream, thick `==>` = primary
> spoken output, dashed `-.->` = on-demand tool calls / data queries.

### How it works (in plain English)

Tuntun.In turns a phone into a pair of smart eyes and ears, worn on the
chest. Three things happen at once:

1. **It watches** — a fast, always-on AI (the *Reflex Layer*) sees the road
   through the camera and, in under a second, speaks warnings out loud:
   *"manhole ahead, step right."*
2. **It thinks** — a slower, on-demand AI (the *Reasoning Layer*) plans
   walking routes that steer around known hazards, but only when asked.
3. **It protects** — when the agent detects life-threatening danger, it
   automatically texts a live-camera link to a family guardian over
   WhatsApp so they can guide the user verbally. Every hazard it spots is
   also quietly logged to a shared public map so other blind pedestrians
   can avoid the same bad road.

> Think of it as a nervous system: a fast **spinal-cord reflex** for instant
> danger, and a slow **cortex** for route planning — never blocking the
> safety-critical path.

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
