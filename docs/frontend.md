# Frontend Guidelines

TypeScript, Vite 7, React 19, npm. ESLint enforced (line-length=120).

## Stack

- **Build tool**: Vite with `@vitejs/plugin-react`
- **Styling**: Tailwind CSS v4 via `@tailwindcss/vite`
- **Routing**: React Router v7 (`react-router-dom`)
- **Dev server**: port 3000, proxies `/api/*` → `http://localhost:8000`

## Style

- 2-space indent, no trailing semicolons (ASI preferred)
- Use path alias `@/` mapped to `src/` in `tsconfig.json`

## Components

- One component per file. Default exports for pages, named exports for shared components.
- Styling: Tailwind utility classes inline. No CSS modules.

## TypeScript

- Strict mode. Prefer `type` over `interface`.
- Keep component props typed inline unless reused across files.

## State & Data

- Local state with `useState`/`useReducer`.
- Server data via `fetch` against the backend API (`/api/*`). Wrap in custom hooks in `src/hooks/`.
- SSE live updates via `EventSource` (`/api/events`).

## Testing

Type-checking only: `npx tsc --noEmit`. No runtime tests.

## Proxy

Vite dev server proxies `/api/*` to `http://localhost:8000` (strips `/api` prefix). Production
deployments should configure the same at the reverse-proxy level.
