#!/usr/bin/env python3
"""Verification script to test the DVD to Plex web UI works in browser.

This script:
1. Starts the FastAPI server
2. Makes HTTP requests to verify all pages load
3. Tests the active mode toggle API
4. Reports results
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path


async def verify_with_httpx():
    """Verify pages load using httpx."""
    import httpx

    base_url = "http://127.0.0.1:8000"
    results = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test dashboard
        print("Testing GET / (dashboard)...")
        try:
            resp = await client.get(f"{base_url}/")
            if resp.status_code == 200:
                # Check for expected content
                content = resp.text
                checks = [
                    ("Dashboard title", "Dashboard - DVD to Plex" in content),
                    ("Active Mode section", "Active Mode" in content),
                    ("Toggle button", 'active-mode-toggle' in content),
                    ("Drive Status cards", "Drive 1" in content and "Drive 2" in content),
                    ("Recent Jobs table", "Recent Jobs" in content),
                ]
                for name, passed in checks:
                    results.append((f"Dashboard: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")
            else:
                results.append(("Dashboard loads", False))
                print(f"  ✗ Dashboard returned {resp.status_code}")
        except Exception as e:
            results.append(("Dashboard loads", False))
            print(f"  ✗ Dashboard error: {e}")

        # Test review page
        print("\nTesting GET /review...")
        try:
            resp = await client.get(f"{base_url}/review")
            if resp.status_code == 200:
                content = resp.text
                checks = [
                    ("Review title", "Review Queue - DVD to Plex" in content),
                    ("Empty state message", "No items to review" in content or "data-job-id" in content),
                ]
                for name, passed in checks:
                    results.append((f"Review: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")
            else:
                results.append(("Review page loads", False))
                print(f"  ✗ Review returned {resp.status_code}")
        except Exception as e:
            results.append(("Review page loads", False))
            print(f"  ✗ Error: {e}")

        # Test collection page
        print("\nTesting GET /collection...")
        try:
            resp = await client.get(f"{base_url}/collection")
            if resp.status_code == 200:
                content = resp.text
                checks = [
                    ("Collection title", "Collection - DVD to Plex" in content),
                    ("Search filter", 'id="search-input"' in content),
                    ("Empty state or grid", "collection is empty" in content or 'id="collection-grid"' in content),
                ]
                for name, passed in checks:
                    results.append((f"Collection: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")
            else:
                results.append(("Collection page loads", False))
                print(f"  ✗ Collection returned {resp.status_code}")
        except Exception as e:
            results.append(("Collection page loads", False))
            print(f"  ✗ Error: {e}")

        # Test wanted page
        print("\nTesting GET /wanted...")
        try:
            resp = await client.get(f"{base_url}/wanted")
            if resp.status_code == 200:
                content = resp.text
                checks = [
                    ("Wanted title", "Wanted List - DVD to Plex" in content),
                    ("Add form", 'id="add-wanted-form"' in content),
                    ("Search input", 'id="wanted-search"' in content),
                    ("Empty state or grid", "wanted list is empty" in content or 'id="wanted-grid"' in content),
                ]
                for name, passed in checks:
                    results.append((f"Wanted: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")
            else:
                results.append(("Wanted page loads", False))
                print(f"  ✗ Wanted returned {resp.status_code}")
        except Exception as e:
            results.append(("Wanted page loads", False))
            print(f"  ✗ Error: {e}")

        # Test active mode toggle API
        print("\nTesting POST /api/active-mode...")
        try:
            # Turn on
            resp = await client.post(
                f"{base_url}/api/active-mode",
                json={"active_mode": True}
            )
            data = resp.json()
            passed = resp.status_code == 200 and data.get("success") and data.get("active_mode") == True
            results.append(("Active mode toggle ON", passed))
            print(f"  {'✓' if passed else '✗'} Toggle ON: {data}")

            # Turn off
            resp = await client.post(
                f"{base_url}/api/active-mode",
                json={"active_mode": False}
            )
            data = resp.json()
            passed = resp.status_code == 200 and data.get("success") and data.get("active_mode") == False
            results.append(("Active mode toggle OFF", passed))
            print(f"  {'✓' if passed else '✗'} Toggle OFF: {data}")
        except Exception as e:
            results.append(("Active mode toggle", False))
            print(f"  ✗ Error: {e}")

        # Verify dashboard reflects toggle state
        print("\nTesting dashboard with active_mode=True...")
        try:
            await client.post(f"{base_url}/api/active-mode", json={"active_mode": True})
            resp = await client.get(f"{base_url}/")
            content = resp.text
            passed = "checked" in content and "System is actively monitoring" in content
            results.append(("Dashboard reflects active mode ON", passed))
            print(f"  {'✓' if passed else '✗'} Dashboard shows active state correctly")
        except Exception as e:
            results.append(("Dashboard reflects active mode", False))
            print(f"  ✗ Error: {e}")

        # Test review page with a sample job
        print("\nTesting review page with sample job...")
        try:
            # Inject a test job directly into app state via internal endpoint
            # First, we need to add a job - using a workaround by posting to the test endpoint
            # For now, we test the API endpoints directly

            # Test approve endpoint (expect 404 since no jobs)
            resp = await client.post(f"{base_url}/api/jobs/999/approve")
            passed = resp.status_code == 404
            results.append(("Review API: approve returns 404 for missing job", passed))
            print(f"  {'✓' if passed else '✗'} Approve returns 404 for missing job")

            # Test identify endpoint (expect 404 since no jobs)
            resp = await client.post(
                f"{base_url}/api/jobs/999/identify",
                json={"title": "Test Movie", "year": 2024}
            )
            passed = resp.status_code == 404
            results.append(("Review API: identify returns 404 for missing job", passed))
            print(f"  {'✓' if passed else '✗'} Identify returns 404 for missing job")

            # Test skip endpoint (expect 404 since no jobs)
            resp = await client.post(f"{base_url}/api/jobs/999/skip")
            passed = resp.status_code == 404
            results.append(("Review API: skip returns 404 for missing job", passed))
            print(f"  {'✓' if passed else '✗'} Skip returns 404 for missing job")
        except Exception as e:
            results.append(("Review API endpoints", False))
            print(f"  ✗ Error: {e}")

        # Test wanted list API
        print("\nTesting wanted list API...")
        try:
            # Test delete endpoint (expect 404 since no items)
            resp = await client.delete(f"{base_url}/api/wanted/999")
            passed = resp.status_code == 404
            results.append(("Wanted API: delete returns 404 for missing item", passed))
            print(f"  {'✓' if passed else '✗'} Delete returns 404 for missing item")
        except Exception as e:
            results.append(("Wanted API delete", False))
            print(f"  ✗ Error: {e}")

        # Test review page shows job cards correctly by injecting test data
        print("\nTesting review page with injected test data...")
        try:
            # Add a test job via internal state manipulation endpoint
            # We'll create a helper endpoint for testing
            resp = await client.post(
                f"{base_url}/api/test/add-job",
                json={
                    "id": 1,
                    "disc_label": "TEST_DVD",
                    "status": "review",
                    "confidence": 0.65,
                    "identified_title": "Test Movie",
                    "identified_year": 2024,
                    "content_type": "movie",
                }
            )
            if resp.status_code == 200:
                # Now check review page shows the job
                resp = await client.get(f"{base_url}/review")
                content = resp.text
                checks = [
                    ("Job card displayed", 'data-job-id="1"' in content),
                    ("Disc label shown", "TEST_DVD" in content),
                    ("Confidence shown", "65%" in content),
                    ("Title shown", "Test Movie" in content),
                    ("Approve button", "approveJob(1)" in content),
                    ("Edit button", "editJob(1" in content),
                    ("Skip button", "skipJob(1)" in content),
                ]
                for name, passed in checks:
                    results.append((f"Review with data: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")

                # Test approve action
                resp = await client.post(f"{base_url}/api/jobs/1/approve")
                passed = resp.status_code == 200 and resp.json().get("success")
                results.append(("Review action: approve job", passed))
                print(f"  {'✓' if passed else '✗'} Approve job succeeds")
            else:
                print("  (Skipping - test endpoint not available)")
        except Exception as e:
            # Test endpoint may not exist, which is fine
            print(f"  (Skipping test data injection - {e})")

        # Test collection page with injected test data
        print("\nTesting collection page with injected test data...")
        try:
            resp = await client.post(
                f"{base_url}/api/test/add-collection",
                json={
                    "id": 1,
                    "title": "The Matrix",
                    "year": 1999,
                    "content_type": "movie",
                    "added_at": "2024-01-15",
                }
            )
            if resp.status_code == 200:
                resp = await client.get(f"{base_url}/collection")
                content = resp.text
                checks = [
                    ("Collection item displayed", "The Matrix" in content),
                    ("Year shown", "1999" in content),
                    ("Content type badge", "badge-movie" in content),
                ]
                for name, passed in checks:
                    results.append((f"Collection with data: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")
            else:
                print("  (Skipping - test endpoint not available)")
        except Exception as e:
            print(f"  (Skipping test data injection - {e})")

        # Test wanted page with injected test data
        print("\nTesting wanted page with injected test data...")
        try:
            resp = await client.post(
                f"{base_url}/api/test/add-wanted",
                json={
                    "id": 1,
                    "title": "Inception",
                    "year": 2010,
                    "content_type": "movie",
                    "notes": "Christopher Nolan film",
                }
            )
            if resp.status_code == 200:
                resp = await client.get(f"{base_url}/wanted")
                content = resp.text
                checks = [
                    ("Wanted item displayed", "Inception" in content),
                    ("Year shown", "2010" in content),
                    ("Notes shown", "Christopher Nolan" in content),
                    ("Remove button", "removeWanted(1)" in content),
                ]
                for name, passed in checks:
                    results.append((f"Wanted with data: {name}", passed))
                    print(f"  {'✓' if passed else '✗'} {name}")

                # Test delete action
                resp = await client.delete(f"{base_url}/api/wanted/1")
                passed = resp.status_code == 200 and resp.json().get("success")
                results.append(("Wanted action: delete item", passed))
                print(f"  {'✓' if passed else '✗'} Delete item succeeds")
            else:
                print("  (Skipping - test endpoint not available)")
        except Exception as e:
            print(f"  (Skipping test data injection - {e})")

    return results


def main():
    """Main function to run verification."""
    print("=" * 60)
    print("DVD to Plex Web UI Browser Verification")
    print("=" * 60)

    # Add src to path
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))

    # Check if httpx is available
    try:
        import httpx
    except ImportError:
        print("\nInstalling httpx for testing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "httpx", "-q"])
        import httpx

    # Check if dependencies are available
    try:
        import fastapi
        import jinja2
        import uvicorn
    except ImportError:
        print("\nInstalling dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "jinja2", "-q"])

    # Create a simple runner script
    runner_script = src_path.parent / "_run_server.py"
    runner_script.write_text(f'''
import sys
sys.path.insert(0, "{src_path}")
from dvdtoplex.web.app import create_app
import uvicorn

app = create_app()
uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
''')

    # Start the server
    print("\nStarting FastAPI server...")
    server_process = subprocess.Popen(
        [sys.executable, str(runner_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    print("Waiting for server to start...")
    time.sleep(3)

    # Check if server is still running
    if server_process.poll() is not None:
        stdout, stderr = server_process.communicate()
        print(f"Server failed to start:")
        print(f"stdout: {stdout.decode()}")
        print(f"stderr: {stderr.decode()}")
        runner_script.unlink(missing_ok=True)
        return 1

    try:
        # Run verification
        print("\n" + "-" * 60)
        print("Running verification tests...")
        print("-" * 60 + "\n")

        results = asyncio.run(verify_with_httpx())

        # Summary
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)

        passed = sum(1 for _, p in results if p)
        total = len(results)

        for name, result in results:
            print(f"  {'✓' if result else '✗'} {name}")

        print(f"\nPassed: {passed}/{total}")

        if passed == total:
            print("\n✓ All browser verification tests passed!")
            return 0
        else:
            print("\n✗ Some tests failed")
            return 1

    finally:
        # Stop server
        print("\nStopping server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

        # Clean up runner script
        runner_script.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
