import argparse
import asyncio
import importlib
import inspect
import sys
import time
from traceback import format_exc

from tests.utils.report_generator import generate_report

# Defined test suites in execution order
SUITES = {
    "smoke": "tests.test_smoke",
    "unit_preprocessor": "tests.test_unit.test_pre_processor",
    "unit_memory": "tests.test_unit.test_memory_store",
    "unit_tools": "tests.test_unit.test_tools",
    "integration": "tests.test_integration.test_orchestrator",
    "workflows": [
        "tests.test_workflows.fake_human_simulator",
        "tests.test_workflows.test_ltm_retrieval",
        "tests.test_workflows.test_tool_orchestration",
    ]
}

def load_tests_from_module(module_name: str):
    try:
        mod = importlib.import_module(module_name)
        test_funcs = []
        for name, obj in inspect.getmembers(mod):
            if inspect.isfunction(obj) and name.startswith("test_"):
                test_funcs.append((name, obj))
        return test_funcs
    except Exception as e:
        print(f"Error loading {module_name}: {e}")
        return []

async def run_test_func(name: str, func) -> dict:
    start_t = time.time()
    passed = False
    error = None
    try:
        if inspect.iscoroutinefunction(func):
            await func()
        else:
            func()
        passed = True
    except AssertionError as e:
        error = str(e) or "AssertionError"
    except Exception as e:
        error = format_exc()
        
    duration = int((time.time() - start_t) * 1000)
    return {
        "name": name,
        "passed": passed,
        "latency_ms": duration,
        "error": error
    }

async def run_suite(suite_name: str, modules) -> dict:
    print(f"\n--- Running Suite: {suite_name} ---")
    if isinstance(modules, str):
        modules = [modules]
        
    suite_results = {"tests": [], "passed": 0, "failed": 0}
    
    for mod_name in modules:
        funcs = load_tests_from_module(mod_name)
        for name, func in funcs:
            sys.stdout.write(f"  {name}... ")
            sys.stdout.flush()
            res = await run_test_func(name, func)
            if res["passed"]:
                print(f"✅ ({res['latency_ms']}ms)")
                suite_results["passed"] += 1
            else:
                print(f"❌ ({res['latency_ms']}ms)")
                print(f"    Error: {res['error'].splitlines()[-1] if res['error'] else 'Unknown'}")
                suite_results["failed"] += 1
            suite_results["tests"].append(res)
            
    return suite_results

async def main():
    parser = argparse.ArgumentParser(description="Sadaf V6 CI Test Runner")
    parser.add_argument("--fast", action="store_true", help="Run smoke and unit tests only")
    parser.add_argument("--full", action="store_true", help="Run all tests including AI workflows")
    parser.add_argument("--suite", type=str, help="Run a specific suite (e.g. smoke, unit_tools)")
    args = parser.parse_args()

    # Determine which suites to run
    to_run = {}
    if args.suite:
        if args.suite in SUITES:
            to_run[args.suite] = SUITES[args.suite]
        else:
            print(f"Unknown suite: {args.suite}. Available: {list(SUITES.keys())}")
            sys.exit(1)
    elif args.fast:
        to_run = {k: v for k, v in SUITES.items() if k in ["smoke", "unit_preprocessor", "unit_memory", "unit_tools"]}
    elif args.full or (not args.fast and not args.suite):
        to_run = SUITES
    
    # Run tests
    overall_start = time.time()
    results = {
        "suites": {},
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "overall_pass": True,
    }
    
    for suite_name, modules in to_run.items():
        suite_res = await run_suite(suite_name, modules)
        results["suites"][suite_name] = suite_res
        results["passed"] += suite_res["passed"]
        results["failed"] += suite_res["failed"]
        results["total_tests"] += (suite_res["passed"] + suite_res["failed"])
        if suite_res["failed"] > 0:
            results["overall_pass"] = False

    results["total_runtime_s"] = time.time() - overall_start

    generate_report(results)
    
    if not results["overall_pass"]:
        sys.exit(1)

if __name__ == "__main__":
    # Workaround for loop issues in some environments
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
