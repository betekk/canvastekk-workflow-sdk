# Pattern: chain mounted FastAPI sub-app lifespans via router.lifespan_context

**Category:** pattern · **Confidence:** high · **Scope:** FastAPI/Starlette composite services (dual-purpose apps mounting sub-apps) · **Date:** 2026-10-31 · **Ticket:** sdk#220

Starlette NEVER runs lifespans of apps mounted via `root.mount(prefix, sub)` —
only the root app's lifespan executes. A mounted SDK node's
`on_startup`/`on_shutdown` wiring silently never fires; tests that only hit
routes stay green while resource setup is dead.

Fix shape (canvastekk_workflow_sdk bootstrap.py `mount_node`): after mounting,
wrap both contexts — `lifespan_context` must be an `@asynccontextmanager`
FACTORY (a bare async generator raises `TypeError: 'async_generator' object
does not support the asynchronous asynchronous context manager protocol` at
server start — the error that reveals this half-done):

    root_lifespan = root_app.router.lifespan_context
    sub_lifespan = sub_app.router.lifespan_context

    @asynccontextmanager
    async def _combined(app):
        async with root_lifespan(app) as rs, sub_lifespan(app) as ss:
            yield {**(rs or {}), **(ss or {})}

    root_app.router.lifespan_context = _combined

Assert with a TestClient context manager + an on_startup flag node — route
tests alone cannot see the gap.
