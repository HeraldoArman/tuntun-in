# Tuntun.In — Agent Coding Guide

Tuntun.In is a multimodal AI mobility companion for visually impaired users.
Turns a chest-mounted smartphone into "smart eyes" using LiveKit WebRTC +
Gemini Live AI for real-time obstacle detection and navigation.

## Architecture

```
tuntun-in/
├── apps/
│   ├── web/            # Next.js 16 PWA — frontend + LiveKit session UI
│   └── agent/          # Python LiveKit agent — Gemini Live + DeepAgents
├── packages/
│   ├── backend/        # Convex — auth, CRUD, realtime data, agent ping
│   ├── ui/             # shadcn/ui new-york (radix-ui) — 45 components
│   ├── config/         # Shared tsconfig
│   └── env/            # @t3-oss/env-nextjs env validation
```

### Data Flow

```
Phone (camera+mic) → LiveKit Cloud (WebRTC) → apps/agent (Python)
  → Gemini Live (google.realtime.RealtimeModel)
  → audio response → back through LiveKit → phone speaker

apps/agent → ConvexClient → Convex Cloud (write obstacles, read preferences)
apps/web → Convex (auth, CRUD, realtime) + /api/token → LiveKit Cloud
```

### Dual-Brain AI

- **Brain 1 (Reflex):** `TuntunAgent` — Gemini Live, instant audio-visual
  obstacle warnings, sub-second latency. `video_input=True`.
- **Brain 2 (Reasoning):** LangChain DeepAgents — multi-step route
  orchestration. Not yet implemented; `deepagents>=0.6.12` is in deps.
- **Handoff:** `session.update_agent(ReasoningAgent())` — but
  `gemini-3.1-flash-live-preview` doesn't support mid-session handoff.

---

## Quick Reference

### Format & Lint (JS/TS)
- **Format code**: `pnpm dlx ultracite fix`
- **Check for issues**: `pnpm dlx ultracite check`
- **Diagnose setup**: `pnpm dlx ultracite doctor`

### Lint & Format (Python)
- **Check**: `cd apps/agent && uv run ruff check .`
- **Format**: `cd apps/agent && uv run ruff format .`

### Dev Commands
- `pnpm run dev` — Start all JS/TS apps
- `pnpm run dev:web` — Start Next.js only
- `pnpm run dev:agent` — Start Python agent (uv run python src/agent.py dev)
- `pnpm run check-types` — TypeScript check across monorepo
- `pnpm run check:agent` — Ruff lint Python agent

### Testing
No tests. This project skips testing — focus on manual QA + logging.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind v4, shadcn/ui (new-york) |
| PWA | manifest.ts, service worker via Next.js |
| WebRTC | LiveKit Cloud — `@livekit/components-react`, `livekit-client` |
| Token server | `livekit-server-sdk` — `POST /api/token` in apps/web |
| Backend DB | Convex Cloud — auth, CRUD, realtime |
| Auth | Better-Auth (email/password, convex plugin) |
| Agent | Python `livekit-agents[google]~=1.6` + `deepagents>=0.6.12` |
| AI model | Gemini Live — `google.realtime.RealtimeModel` |
| Python mgr | uv (astral-sh) |
| Monorepo | Nx + pnpm workspaces |
| Lint JS/TS | Ultracite/Biome |
| Lint Python | ruff |
| Deploy | Railway (agent + web) + LiveKit Cloud + Convex Cloud |

---

## Core Principles

Write code that is **accessible, performant, type-safe, and maintainable**.
Focus on clarity and explicit intent over brevity.

### Type Safety & Explicitness

- Use explicit types for function parameters and return values when they enhance clarity
- Prefer `unknown` over `any` when the type is genuinely unknown
- Use const assertions (`as const`) for immutable values and literal types
- Leverage TypeScript's type narrowing instead of type assertions
- Use meaningful variable names instead of magic numbers - extract constants with descriptive names

### Modern JavaScript/TypeScript

- Use arrow functions for callbacks and short functions
- Prefer `for...of` loops over `.forEach()` and indexed `for` loops
- Use optional chaining (`?.`) and nullish coalescing (`??`) for safer property access
- Prefer template literals over string concatenation
- Use destructuring for object and array assignments
- Use `const` by default, `let` only when reassignment is needed, never `var`

### Async & Promises

- Always `await` promises in async functions - don't forget to use the return value
- Use `async/await` syntax instead of promise chains for better readability
- Handle errors appropriately in async code with try-catch blocks
- Don't use async functions as Promise executors

### React & JSX

- Use function components over class components
- Call hooks at the top level only, never conditionally
- Specify all dependencies in hook dependency arrays correctly
- Use the `key` prop for elements in iterables (prefer unique IDs over array indices)
- Nest children between opening and closing tags instead of passing as props
- Don't define components inside other components
- Use semantic HTML and ARIA attributes for accessibility:
  - Provide meaningful alt text for images
  - Use proper heading hierarchy
  - Add labels for form inputs
  - Include keyboard event handlers alongside mouse events
  - Use semantic elements (`<button>`, `<nav>`, etc.) instead of divs with roles

### Error Handling & Debugging

- Remove `console.log`, `debugger`, and `alert` statements from production code
- Throw `Error` objects with descriptive messages, not strings or other values
- Use `try-catch` blocks meaningfully - don't catch errors just to rethrow them
- Prefer early returns over nested conditionals for error cases

### Code Organization

- Keep functions focused and under reasonable cognitive complexity limits
- Extract complex conditions into well-named boolean variables
- Use early returns to reduce nesting
- Prefer simple conditionals over nested ternary operators
- Group related code together and separate concerns

### Security

- Add `rel="noopener"` when using `target="_blank"` on links
- Avoid `dangerouslySetInnerHTML` unless absolutely necessary
- Don't use `eval()` or assign directly to `document.cookie`
- Validate and sanitize user input
- Server-to-server secrets (CONVEX_SERVICE_SECRET) must never be exposed to client

### Performance

- Avoid spread syntax in accumulators within loops
- Use top-level regex literals instead of creating them in loops
- Prefer specific imports over namespace imports
- Avoid barrel files (index files that re-export everything)
- Use proper image components (e.g., Next.js `<Image>`) over `<img>` tags

### Framework-Specific Guidance

**Next.js:**

- Use Next.js `<Image>` component for images
- Use `next/head` or App Router metadata API for head elements
- Use Server Components for async data fetching instead of async Client Components

**React 19+:**

- Use ref as a prop instead of `React.forwardRef`

**Solid/Svelte/Vue/Qwik:**

- Use `class` and `for` attributes (not `className` or `htmlFor`)

---

## Python Agent (apps/agent/)

### Logging — Maximum Verbosity

The agent logs **everything** — every lifecycle event, tool call, error,
state transition, timing measurement. This is by design for debugging.

- **LOG_LEVEL env var** — default `INFO`, set to `DEBUG` for verbose lib logs
- **Format**: `%(asctime)s [%(levelname)s] %(name)s:%(lineno)d — %(message)s`
- **Output**: stdout (Railway captures automatically)
- **DEBUG mode** enables: livekit, livekit.agents, livekit.rtc, convex,
  google, google.genai, httpx, websockets
- **Timing**: every significant operation logs elapsed milliseconds
- **Errors**: `exc_info=True` on all error logs — full stack traces
- **Startup**: logs all env var state (secrets redacted as "set"/"not set")

### Agent Lifecycle

1. `entrypoint(ctx)` — new room session, logs room name + job id
2. `_get_convex_client()` — creates ConvexClient, logs success/failure
3. `_ping_convex(client, label)` — verifies DB connectivity, logs timing
4. `AgentSession()` created, logs elapsed
5. `session.start(agent=TuntunAgent(), room=ctx.room, room_options=...)`
6. `TuntunAgent.__init__` — logs model, voice, temperature
7. `TuntunAgent.on_enter` — generates greeting, logs timing
8. `TuntunAgent.on_exit` — logs departure

### Run Modes

```bash
cd apps/agent
uv run python src/agent.py dev       # dev mode, waits for frontend
uv run python src/agent.py console   # terminal test, no LiveKit
uv run python src/agent.py start     # production
```

### Env Vars

| Var | Required | Description |
|---|---|---|
| LIVEKIT_URL | yes | wss://project.livekit.cloud |
| LIVEKIT_API_KEY | yes | LiveKit API key |
| LIVEKIT_API_SECRET | yes | LiveKit API secret |
| GOOGLE_API_KEY | yes | Gemini API key (aistudio.google.com) |
| CONVEX_URL | no | Convex cloud URL (enables DB persistence) |
| CONVEX_SERVICE_SECRET | no | Shared secret for agent:ping mutation |
| LOG_LEVEL | no | DEBUG/INFO/WARNING/ERROR (default: INFO) |

---

## Convex Backend (packages/backend/)

### Schema Tables

| Table | Purpose |
|---|---|
| `todos` | Existing Better-T-Stack todo CRUD (unchanged) |
| `obstacles` | Crowdsourced hazard reports (lat, lng, type, severity) |
| `trips` | User trip sessions (roomName, userId, startedAt, status) |
| `emergency_rooms` | Overwatch family viewer sessions (roomName, familyIdentity) |

### Agent Ping

`agent:ping` mutation — called by Python agent on session start to verify
DB connectivity. Protected by `CONVEX_SERVICE_SECRET` env var, not user auth.

```typescript
// packages/backend/convex/agent.ts
export const ping = mutation({
  args: { secret: v.string() },
  handler: async (_ctx, { secret }) => {
    if (secret !== process.env.CONVEX_SERVICE_SECRET) {
      throw new Error("unauthorized");
    }
    return { ok: true, timestamp: Date.now() };
  },
});
```

### Python → Convex Integration

Python agent uses official `convex` Python client:

```python
from convex import ConvexClient
client = ConvexClient(os.environ["CONVEX_URL"])
result = client.mutation("agent:ping", {"secret": secret})
```

Real-time subscriptions also supported: `client.subscribe("query:name", args)`.

---

## LiveKit Integration

### Frontend Token Endpoint

`apps/web/src/app/api/token/route.ts` — POST handler that mints LiveKit
access tokens with `RoomAgentDispatch` for `tuntun-agent`.

### Frontend Session UI

`apps/web/src/app/agent/page.tsx` — minimal page using:
- `useSession(TokenSource.endpoint("/api/token"))`
- `SessionProvider` + `RoomAudioRenderer`
- No header nav link (navigate manually to `/agent`)

### Adding LiveKit @agents-ui Components

Both `components.json` files have the `@agents-ui` registry configured:

```bash
pnpm dlx shadcn@latest add @agents-ui/agent-control-bar -c packages/ui
```

---

## shadcn/ui

- **Style**: new-york (radix-ui primitives)
- **Location**: `packages/ui/src/components/` — 45 components
- **Registry**: `@agents-ui` at `https://livekit.io/ui/r/{name}.json`
- **Add components**: `pnpm dlx shadcn@latest add <name> -c packages/ui`

---

## When Biome Can't Help

Biome's linter will catch most issues automatically. Focus your attention on:

1. **Business logic correctness** - Biome can't validate your algorithms
2. **Meaningful naming** - Use descriptive names for functions, variables, and types
3. **Architecture decisions** - Component structure, data flow, and API design
4. **Edge cases** - Handle boundary conditions and error states
5. **User experience** - Accessibility, performance, and usability considerations
6. **Documentation** - Add comments for complex logic, but prefer self-documenting code
7. **Logging** - Python agent must log every lifecycle event with timing

---

Most formatting and common issues are automatically fixed by Biome. Run
`pnpm dlx ultracite fix` before committing to ensure compliance.
For Python, run `cd apps/agent && uv run ruff check . && uv run ruff format .`