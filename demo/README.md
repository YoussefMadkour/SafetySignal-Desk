# Demo assets — backup clip

A network-proof backup of the autonomous Band run, in case the venue blocks
WebSockets or Band is unreachable during the pitch.

- **`replay.py`** — a deterministic, offline re-creation of
  `python -m safety_signal.run_agents --auto-approve`, with the same colored,
  paced terminal output. **Touches no network and cannot fail.** Use it as the
  backup clip source or as a live fallback.
- **`autonomous_run.log`** — raw captured output from a real live run against
  Band (room `55a9cb21-…`), proving the real system works.

## Play it

```bash
python demo/replay.py          # demo speed (paced, ~25s)
python demo/replay.py --fast   # instant (for a quick capture)
```

## Record a clip

**Option A — QuickTime (macOS, no install):**
1. QuickTime Player → File → New Screen Recording → record your terminal.
2. Run `python demo/replay.py` in a large, dark terminal.
3. Stop; export the `.mov` (trim if needed).

**Option B — asciinema (if installed):**
```bash
brew install asciinema       # one-time
asciinema rec demo/run.cast -c "python demo/replay.py"
# play back: asciinema play demo/run.cast
# or upload for a shareable link: asciinema upload demo/run.cast
```

**Option C — terminal-to-GIF** (e.g. `vhs`, `terminalizer`) if you want a GIF
for the submission page.

## Pitch pairing

Run `replay.py` in the terminal while showing the Band web room (app.band.ai) on
the live run — the replay narrates the same handoffs. The line to land:
*"Nothing in Python sequences this — Band delivers each @mention, agents read
context from the Band message, and Regulatory Risk converges only once all
prerequisites have arrived in the room."*
