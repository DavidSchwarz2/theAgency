# Frontend Guidelines

TypeScript, Next.js 16 (App Router), React 19, pnpm. **Biome v2 enforced** (line-width=120).

## Style

- 2-space indent, semicolons as-needed (ASI)
- Use `@/` path alias (`@/components/ui/button`)

## Components

- One component per file. Default exports for pages/layouts, named exports for utilities.
- **UI**: shadcn/ui (new-york style) + Radix primitives in `components/ui/`. Use `cn()` from `@/lib/utils`.
- **Styling**: Tailwind CSS v4, utility classes inline.

## TypeScript

- Strict mode, target ES2017. Prefer `type` over `interface`.
- Zod schemas in `types/<domain>.types.ts`, infer with `z.infer<typeof schema>`.

## State & Data

- Zustand stores in `stores/`.
- TanStack React Query from server actions.

## Server Actions

- `"use server"` directive in `actions/`
- Pure HTTP client wrappers to `process.env.API_URL` — zero business logic.
- Return typed responses. Throw `Error` on non-ok responses.

## Testing

Type-checking only: `tsc --noEmit`. No runtime tests.

## Proxy (Middleware)

Next.js 16 renamed `middleware.ts` → `proxy.ts` and the exported function from `middleware()` → `proxy()`.
The active proxy file is `apps/frontend/proxy.ts` — it is **not dead code**. It handles JWT cookie
validation and redirects unauthenticated users to `/login` for all protected routes.
