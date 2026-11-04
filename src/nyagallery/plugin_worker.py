from __future__ import annotations

import importlib.util
import json
import sys


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    spec = importlib.util.spec_from_file_location("nyagallery_sandbox_plugin", sys.argv[1])
    if spec is None or spec.loader is None:
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    start = getattr(module, "start", None)
    stop = getattr(module, "stop", None)
    if not callable(start) or not callable(stop):
        return 3
    for line in sys.stdin:
        try:
            action = json.loads(line).get("action")
            if action == "start":
                start()
            elif action == "stop":
                stop()
            else:
                raise ValueError("unknown plugin action")
            print(json.dumps({"ok": True, "action": action}), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
