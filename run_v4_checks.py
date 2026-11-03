"""Software tests; provider behavior is tested with mocks, never billed API calls."""
from datetime import datetime,timezone
from pathlib import Path
import json,unittest


def main():
    root=Path(__file__).resolve().parent
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root/'tests')))
    report=dict(project='Greenhouse IoT Lab',version='4.0.0',created_at=datetime.now(timezone.utc).isoformat(),
        software_tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        software_checks_passed=result.wasSuccessful(),gemini_live_api='NOT_EXECUTED',
        gemini_test_scope='Mocked provider responses, strict selection validation and local fallback',
        hardware_validation='PENDING',esp32_compilation='NOT_EXECUTED',windows_gui_execution='NOT_EXECUTED',physical_actuation=False)
    folder=root/'exports';folder.mkdir(exist_ok=True)
    path=folder/'v4_software_validation.json';path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('\nReport:',path)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
