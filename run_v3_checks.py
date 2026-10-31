"""Run software checks and export a report without claiming hardware validation."""
from datetime import datetime,timezone
from pathlib import Path
import json
import unittest

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    suite=unittest.defaultTestLoader.discover(str(root/'tests'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(project='Greenhouse IoT Lab',version='3.0.0',
        created_at=datetime.now(timezone.utc).isoformat(),software_tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        software_checks_passed=result.wasSuccessful(),hardware_validation='PENDING',
        esp32_compilation='NOT_EXECUTED',windows_gui_execution='NOT_EXECUTED',physical_actuation=False,
        scope='Temporary SQLite databases and loopback HTTP tests; no sensor field validation.')
    dest=root/'exports';dest.mkdir(exist_ok=True)
    output=dest/'v3_software_validation.json';output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('\nReport:',output)
    raise SystemExit(0 if result.wasSuccessful() else 1)
