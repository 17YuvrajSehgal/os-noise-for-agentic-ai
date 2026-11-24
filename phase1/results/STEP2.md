# Step 2 results: the model wait and the network (P6, P7, P8, P20)

Date: 2026-11-10. Data: all 262 traces. Tables are for the coding-task runs
unless said otherwise.

How to rerun (about 1 minute):

```bash
export OSNOISE_RUNS=C:/workplace/microservice-trace-dataset/agentic-runs
cd phase1
python parse_all.py > results/parsed_all.jsonl
python step2.py                              # -> results/step2_runs.csv, step2_turns.csv
python p20_wire.py > results/p20_wire.csv    # packet headers: round-trip time, retransmissions
```

Destinations were identified by resolving host names on 2026-11-10. The
runs are from October, so treat the names as likely, not certain.
`160.79.104.10` is `api.anthropic.com`. `104.18.2.115` and `104.18.3.115`
are `openrouter.ai`. `104.18.32.47` matches `chatgpt.com`. `34.149.66.165`
is a Google Cloud address of unknown purpose.

## P6. Anatomy of a model turn

Median, with the 90th percentile after the slash:

| Agent, CPU setting | Turns | Wait for first byte (s) | Streaming (s) | Request (KB) | Response (KB) | Response rate (KB/s) |
|---|---|---|---|---|---|---|
| Claude, unlimited | 38 | 1.13 / 4.17 | 1.26 / 6.24 | 3.9 | 3.2 | 1.8 |
| Claude, 1 core | 44 | 1.11 / 3.94 | 1.69 / 5.37 | 3.6 | 3.2 | 1.8 |
| Claude, 0.5 core | 38 | 1.12 / 3.98 | 0.81 / 7.01 | 4.2 | 3.1 | 1.9 |
| Claude, 0.25 core | 35 | 1.10 / 3.90 | 0.81 / 6.82 | 4.2 | 3.1 | 1.7 |
| Codex, unlimited | 102 | 0.70 / 1.75 | 1.75 / 3.67 | 64.1 | 17.8 | 10.9 |
| Codex, 1 core | 94 | 0.62 / 1.66 | 1.75 / 3.35 | 63.5 | 18.6 | 11.7 |
| Codex, 0.5 core | 87 | 0.77 / 1.62 | 1.78 / 4.18 | 63.6 | 19.2 | 10.3 |
| Codex, 0.25 core | 97 | 0.63 / 1.48 | 1.67 / 3.78 | 63.4 | 18.3 | 10.2 |

What this means:

- **A CPU cap does not touch the model turn.** Wait for first byte and
  streaming time are the same at every CPU setting, for both agents. This
  confirms the Step 1 result from a second angle.
- **A turn is about 1 s of waiting plus 1 to 2 s of streaming.** The wait
  for the first byte has a long tail (90th percentile about 4 s for Claude).
- **Responses are tiny and slow.** 1.8 KB/s for Claude, 11 KB/s for Codex.
  The model produces text much slower than any network can carry it.
- **Upload time is not visible at this level.** The kernel accepts the
  whole request into its send buffer at once, so the write returns in under
  a millisecond.
- Not explained: the longest pause inside a Codex stream is 0.42 s in
  almost every turn. It looks like a fixed feature of that service.

## P7. Connections

Unlimited coding runs, median per run:

| | Claude Code | Codex |
|---|---|---|
| HTTPS connection attempts | 23 | 13 |
| Connections that carried data | 14 | 13 |
| Connections used for model turns | 1 | 10 |
| Model turns | 3 | 10 |
| Set-up time before a model request on a new connection | once, at start-up | 26 ms per turn |
| Round-trip time to the model endpoint | 10.8 ms | 10.8 ms |

- **Claude Code opens one model connection at start-up and reuses it** for
  every turn. Nine of its 23 connection attempts carry no data (IPv6
  attempts and address probes that are dropped).
- **Codex opens a new connection for every turn.** The set-up (TCP plus
  TLS) costs 26 ms each time, which is about 2.5 round trips. At today's
  10.8 ms round trip this is under 1% of the run.
- **DNS is cheap**: Claude Code does about 7 lookups per run through the
  local resolver, each under 4 ms. Codex's lookups are not visible with
  this method.

## P8. Other network traffic

Unlimited coding runs, median per run:

| | Claude Code | Codex |
|---|---|---|
| Model turns: sent / received | 38 KB / 13.5 KB | 640 KB / 191 KB |
| Other HTTPS: exchanges | 36 | 16 |
| Other HTTPS: sent / received | 216 KB / 239 KB | 544 KB / 89 KB |
| Time with only non-model requests in flight | 1.59 s | 0.34 s |

Where the other traffic goes:

- **Claude Code**: about 34 exchanges with `api.anthropic.com` (101 KB sent,
  236 KB received), mostly at start-up, and 3 exchanges with the unknown
  Google Cloud address (131 KB sent) near the end of the run.
- **Codex**: about 4 exchanges with the `chatgpt.com` address (531 KB sent,
  most of it in one upload at the end), 10 small ones with `openrouter.ai`,
  and a `git` fetch from `github.com` at start-up.

What this means:

- **Most of Claude Code's bytes are not model traffic**: 85% of the bytes it
  sends and 95% of the bytes it receives belong to start-up configuration
  and uploads at exit.
- **This is why the old 84% figure was too high.** The old method counted
  these exchanges as model time (1.6 s per Claude run).
- For a network limit, the start-up and exit traffic is the larger volume,
  so a bandwidth limit would stretch start-up and shutdown before it
  touches the model turns.

## P20. Was the network clean?

From the TCP headers of every packet on port 443, all 262 runs:

- **Retransmissions: zero** in about 35,000 data segments sent.
- **Round-trip time: 10.8 ms** to both model endpoints (range 10.5 to 13.4
  ms), measured from SYN to SYN-ACK.

So the network was not a hidden factor in any existing result.

## What this decides for the network experiment

- **Bandwidth limits will matter only when very tight.** A whole Claude run
  moves about 500 KB and a Codex run about 1.5 MB. Model responses arrive
  at 2 to 11 KB/s. A limit has to be near or below about 1 Mbit/s before
  it can bite, and it will hit start-up, exit uploads and Codex's 64 KB
  requests first.
- **Delay is the interesting knob.** The baseline round trip is 10.8 ms.
  Each new connection costs about 2.5 round trips, so added delay costs
  Codex on every turn (10 turns) and Claude Code only at start-up (about 14
  connections). Prediction: with 100 ms added, Codex gains about 0.25 s per
  turn and Claude Code gains mainly at start-up.
- **Loss is untested and may matter most.** A lost packet costs at least a
  retransmission timeout (about 200 ms or more), against a 1 s wait for the
  first byte.
- Suggested grid: delay 0, 50, 100, 200 ms; loss 0, 1, 5%; bandwidth
  unlimited, 1 Mbit/s, 256 kbit/s.

## Open questions

- Why Claude Code's later requests are only about 4 KB (compressed bodies
  is a guess).
- What the unknown Google Cloud address and the `chatgpt.com` uploads are.
  The trace shows sizes and timing, not content.
- The tables use the coding runs. The same numbers exist for the other
  families in the CSV files.
