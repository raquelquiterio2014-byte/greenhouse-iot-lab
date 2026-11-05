"""Run isolated end-to-end checks with real loopback HTTP and synthetic samples."""
from datetime import datetime, timezone
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import time

from . import __version__
from .analysis import AnalysisService
from .connectivity import summarize
from .core import Store
from .device_client import DeviceClient, Outbox, post_json
from .receiver import Receiver

SCENARIOS = {
    "normal": ("SCREENED", None),
    "reconnect_heat": ("REVIEW_REQUIRED", "ABOVE_LIMIT"),
    "stale": ("BLOCKED", "STALE_DATA"),
    "sensor_fault": ("BLOCKED", "SENSOR_FAULT_HEARTBEAT"),
}


def evaluate_case(name):
    expected_status, expected_signal = SCENARIOS[name]
    with TemporaryDirectory(prefix="greenhouse-v5-") as folder:
        root = Path(folder)
        store = Store(root / "observations.sqlite3")
        token = secrets.token_hex(24)
        receiver = Receiver(store, token, port=0)
        receiver.start()
        try:
            return _exercise(name, expected_status, expected_signal, root, store, receiver, token)
        finally:
            receiver.stop()


def _exercise(name, expected_status, expected_signal, root, store, receiver, token):
    base = f"http://127.0.0.1:{receiver.port}/api/test"
    ack_lost = False

    def sender(url, key, payload):
        nonlocal ack_lost
        code, body = post_json(url, key, payload)
        if name == "reconnect_heat" and code == 201 and not ack_lost:
            ack_lost = True
            return 0, {}
        return code, body

    box = Outbox(root / "outbox.sqlite3")
    client = DeviceClient(base + "/readings", token, box, sender=sender)
    now = time.time()
    count = 8
    for i in range(count):
        reading = client.sample_payload()
        reading.update(temperature=32 + i if name == "reconnect_heat" else 25,
                       humidity=62, soil_raw=2100, soil_mv=1700, light_raw=864)
        age = 5 * (count - i) + (600 if name == "stale" else 0)
        box.enqueue(reading, now - age)

    client.offline = name == "reconnect_heat"
    offline_retained = (client.send_pending(now) == "offline" and box.count() == count
                        and store.count("test") == 0) if client.offline else None
    client.offline = False
    results = []
    for _ in range(count + 1):
        if not box.count():
            break
        results.append(client.send_pending(time.time()))
        if results[-1] == "retry":
            # Advance the retry clock without waiting; measurement ages remain realistic.
            results.append(client.send_pending(time.time() + 2))
    heartbeat_code, _ = post_json(base + "/heartbeat", token, {
        "device_id": "greenhouse-01",
        "status": "sensor_fault" if name == "sensor_fault" else "ok",
    })
    transport = summarize(store, "test")
    analysis = AnalysisService(store)
    report = analysis.run("test", sensor_status=transport["sensor_status"])
    signals = report["gate_reasons"] + [finding["code"] for finding in report["findings"]]
    checks = {
        "all_samples_delivered_once": box.count() == 0 and client.sent == count and store.count("test") == count,
        "history_isolated": store.count("real") == store.count("demo") == 0,
        "heartbeat_accepted": heartbeat_code == 200,
        "expected_status": report["status"] == expected_status,
        "expected_signal": expected_signal in signals if expected_signal else signals == ["NO_FLAG"],
        "analysis_saved": any(row["run_id"] == report["run_id"] for row in analysis.history("test")),
        "local_only": report["ai"]["engine"] == "NOT_REQUESTED",
        "no_action_authorized": report["authorization"] == "NO_ACTION_AUTHORIZED",
    }
    if name == "reconnect_heat":
        checks["offline_queue_retained"] = offline_retained
        checks["lost_ack_deduplicated"] = ack_lost and transport["counts"]["duplicate"] == 1
    return dict(scenario=name, passed=all(checks.values()), checks=checks,
                expected_status=expected_status, expected_signal=expected_signal,
                transport=transport, delivery_results=results, analysis=report)


def evaluate(names=SCENARIOS):
    cases = [evaluate_case(name) for name in names]
    return dict(version=__version__, created_at=datetime.now(timezone.utc).isoformat(),
                scope="SYNTHETIC_LOOPBACK_HTTP", physical_actuation=False,
                hardware_validation="PENDING", gemini_live_api="NOT_EXECUTED",
                passed=all(case["passed"] for case in cases), cases=cases)
