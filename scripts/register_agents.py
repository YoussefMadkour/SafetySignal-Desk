"""One-time setup: register the 7 specialist agents on Band.

Each agent is registered via the Human API, which returns an API key exactly
once. We persist {agent_key: {agent_id, api_key, name, handle}} to agents.json
(gitignored). Idempotent: agents already present in agents.json are skipped.

Usage:
    python -m scripts.register_agents            # register any missing agents
    python -m scripts.register_agents --reset    # delete ours on Band, re-register
    python -m scripts.register_agents --list     # show current registry
"""
from __future__ import annotations

import sys

from safety_signal import config
from safety_signal.band_client import BandHumanClient


def main(argv: list[str]) -> int:
    if not config.BAND_API_KEY:
        print("ERROR: BAND_API_KEY not set. Copy .env.example to .env and fill it in.")
        return 1

    human = BandHumanClient()
    registry = config.load_agent_registry()

    if "--list" in argv:
        for k, v in registry.items():
            print(f"  {k:18} {v['name']:38} id={v['agent_id']}")
        if not registry:
            print("  (empty — run without --list to register)")
        return 0

    if "--reset" in argv:
        for k, v in list(registry.items()):
            try:
                human.delete_agent(v["agent_id"])
                print(f"deleted {v['name']}")
            except Exception as exc:
                print(f"warn: could not delete {v['name']}: {exc}")
        registry = {}

    print(f"Owner profile: {_safe(lambda: human.profile().get('handle'))}")

    for spec in config.AGENTS:
        if spec.key in registry:
            print(f"skip   {spec.name} (already registered)")
            continue
        try:
            created = human.register_agent(spec.name, spec.handle, spec.role)
        except Exception as exc:
            print(f"ERROR registering {spec.name}: {exc}")
            return 1
        # Band returns {"agent": {...}, "credentials": {"api_key": ...}} (data-unwrapped).
        agent_obj = created.get("agent") or created
        creds = created.get("credentials") or {}
        agent_id = agent_obj.get("id") or created.get("id") or created.get("agent_id")
        api_key = creds.get("api_key") or created.get("api_key") or agent_obj.get("api_key")
        handle = agent_obj.get("handle") or created.get("handle") or spec.handle
        if not agent_id or not api_key:
            print(f"ERROR: registration response for {spec.name} missing id/api_key: {created}")
            return 1
        registry[spec.key] = {
            "agent_id": agent_id, "api_key": api_key,
            "name": spec.name, "handle": handle,
        }
        config.save_agent_registry(registry)
        print(f"OK     {spec.name}  id={agent_id}")

    print(f"\nWrote {len(registry)} agents to {config.BAND_AGENT_KEYS_FILE}")
    return 0


def _safe(fn):
    try:
        return fn()
    except Exception as exc:
        return f"<{exc}>"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
