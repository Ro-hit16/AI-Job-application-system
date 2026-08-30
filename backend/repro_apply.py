import asyncio
import sys
import traceback

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def main():
    loop = asyncio.get_running_loop()
    print("loop_type =", type(loop).__name__)
    print("policy_type =", type(asyncio.get_event_loop_policy()).__name__)

    from app.services.apply_service import ApplyInput, submit_application

    inp = ApplyInput(
        application_id="repro-test-1",
        job_url="https://example.com",
        portal="unknown",
        user_id="repro-user",
        contact_info={"name": "Test User", "email": "test@example.com", "phone": "1234567890"},
        cover_letter="",
        resume_file_path=None,
    )

    result = await submit_application(inp)
    print("\n=== RESULT ===")
    print("status:", result.status)
    print("error_message:", result.error_message)
    print("screenshot_path:", result.screenshot_path)
    print("html_dump_path:", result.html_dump_path)
    print("trace_path:", result.trace_path)
    print("login_verified:", result.login_verified)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("\n=== FULL TRACEBACK ===")
        traceback.print_exc()
        print("=== END TRACEBACK ===")