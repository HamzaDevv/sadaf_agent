import json
import os
from datetime import datetime

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")

def generate_report(results: dict):
    """Generates both JSON and HTML reports from the test results."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(REPORTS_DIR, f"report_{timestamp}.json")
    html_path = os.path.join(REPORTS_DIR, f"report_{timestamp}.html")
    
    # 1. JSON Report
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
        
    # 2. HTML Report
    total_tests = results.get("total_tests", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    overall_pass = results.get("overall_pass", False)
    badge_color = "#28a745" if overall_pass else "#dc3545"
    badge_text = "PASS" if overall_pass else "FAIL"
    
    suites = results.get("suites", {})
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sadaf V6 CI Test Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8f9fa; color: #333; }}
        .container {{ max-width: 1000px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        h1 {{ text-align: center; color: #2c3e50; }}
        .summary {{ display: flex; justify-content: space-around; background: #f1f3f5; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .summary-item {{ text-align: center; font-size: 18px; }}
        .summary-value {{ font-size: 28px; font-weight: bold; margin-top: 5px; }}
        .badge {{ background-color: {badge_color}; color: white; padding: 5px 15px; border-radius: 12px; font-size: 24px; }}
        .suite-card {{ border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 20px; padding: 15px; }}
        .suite-card h2 {{ margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 10px; color: #34495e; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
        .pass {{ color: #28a745; font-weight: bold; }}
        .fail {{ color: #dc3545; font-weight: bold; }}
        pre {{ background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Sadaf V6 CI Test Report</h1>
        <div class="summary">
            <div class="summary-item">Overall Status<div class="summary-value"><span class="badge">{badge_text}</span></div></div>
            <div class="summary-item">Total Tests<div class="summary-value">{total_tests}</div></div>
            <div class="summary-item">Passed<div class="summary-value" style="color: #28a745;">{passed}</div></div>
            <div class="summary-item">Failed<div class="summary-value" style="color: #dc3545;">{failed}</div></div>
            <div class="summary-item">Runtime<div class="summary-value">{results.get("total_runtime_s", 0):.2f}s</div></div>
        </div>
        
        <h2>Test Suites</h2>
"""
    for suite_name, suite_data in suites.items():
        html_content += f"""
        <div class="suite-card">
            <h2>{suite_name.capitalize()} <span style="font-size: 16px; font-weight: normal; color: #666;">(Pass: {suite_data.get('passed')}, Fail: {suite_data.get('failed')})</span></h2>
            <table>
                <tr>
                    <th>Test Name</th>
                    <th>Status</th>
                    <th>Latency (ms)</th>
                    <th>Error/Notes</th>
                </tr>
"""
        for test in suite_data.get("tests", []):
            status_class = "pass" if test.get("passed") else "fail"
            status_text = "✅ PASS" if test.get("passed") else "❌ FAIL"
            error_note = test.get("error", "") or test.get("notes", "")
            
            html_content += f"""
                <tr>
                    <td>{test.get("name")}</td>
                    <td class="{status_class}">{status_text}</td>
                    <td>{test.get("latency_ms", "-")}</td>
                    <td><pre style="margin:0; font-size:12px;">{error_note}</pre></td>
                </tr>
"""
        html_content += """
            </table>
        </div>
"""
    
    html_content += f"""
        <div style="text-align: center; margin-top: 30px; font-size: 14px; color: #888;">
            <p>Generated on {timestamp} | <a href="file://{json_path}" target="_blank">View JSON Source</a></p>
        </div>
    </div>
</body>
</html>
"""
    with open(html_path, "w") as f:
        f.write(html_content)
        
    print(f"\n✅ Reports generated:")
    print(f"  - HTML: {html_path}")
    print(f"  - JSON: {json_path}")
