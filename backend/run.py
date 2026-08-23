import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    # IMPORTANT (Windows + Playwright): uvicorn's `reload=True` sets
    # Config.use_subprocess = True, and uvicorn/loops/asyncio.py's
    # asyncio_setup() then unconditionally forces
    # asyncio.WindowsSelectorEventLoopPolicy() in the actual worker
    # process — overwriting the WindowsProactorEventLoopPolicy set above,
    # in the very process that runs the app, background tasks, and
    # Playwright. WindowsSelectorEventLoop does not support
    # asyncio.create_subprocess_exec(), which Playwright's
    # chromium.launch() relies on internally, so auto-apply fails with
    # NotImplementedError even though a standalone Playwright script
    # (no uvicorn, no reload) works fine.
    #
    # reload=False keeps this as a single process, so the Proactor
    # policy set above is never overridden and Playwright's subprocess
    # creation works exactly as it does in the standalone test.
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        loop="asyncio",
    )