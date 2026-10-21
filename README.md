# Oracle public-call paper study

This is a continuous, read-only observation and software-validation study. It places no orders and uses no Oracle or Kalshi account credentials. It records Oracle's public feed and public Kalshi books and settlements. It does not claim to reproduce Oracle's private order engine.

## Study protocol

- Record every 5 seconds, subject to response times and outages. Preserve acquisition times, errors, call revisions, quoted prices and displayed book depth.
- Use the first **observed locked** UP/DOWN call for a contract; never reconstruct missing calls from winners or aggregate accuracy. Preserve SITOUTs.
- Verify outcomes against Kalshi's finalized market result. Pending settlements stay pending.
- Resume the original recorded history, with no 40-hour stop in continuous mode.
- Evaluate rolling 12/24/36-hour windows ending at the current second, including rounds by closing time (start exclusive, end inclusive), only when their full elapsed duration exists. Report missing rounds and exclude incomplete quote paths from the primary sample; do not describe an incomplete sample as the whole period.
- Paper entry: first usable Kalshi book observed within 15 seconds of the call's seal, on the called side. The first qualifying quote is the entry opportunity; a cap that rejects it skips that call (no hindsight waiting for a cheaper entry).
- Hypothetical stake: up to $1 of contracts per call, **whole contracts**, with entry fees additional. Cap quantity at displayed best-ask depth. Actual fills and the bot's sizing rules remain unverified.
- Buy caps: 1–99 cents in 1-cent steps, plus OFF. Actual quotes may be sub-cent; the cap itself is a whole-cent setting.
- Display the optimized maximum buy cap separately from average entry: the unweighted mean observed price per purchase before fees, using only calls accepted by that cap. Show how many otherwise eligible calls the cap skipped. Rank by total net profit, even when the winning cap skips rounds or has lower ROI.
- TP: 0–100% gain in 1% steps, plus OFF. SL: 0–100% loss in 5% steps, plus OFF. Triggers are relative to the purchase price, before fees.
- A trigger executes at the **next sampled book**, walking the displayed bid levels. If the recorded depth cannot fill the entire position, wait for the next recorded book. Positions still open settle at the official result. This deliberately specified paper execution policy is not a verified reproduction of Oracle's implementation.
- Use the captured series fee type/multiplier, quadratic taker fees, six-decimal fee rounding and direct-member $0.0001 balance rounding. No settlement fee. Report the assumed fee basis.
- Reject contradictory calls, stale/slow entry data, gaps over 20 seconds after the entry opportunity, or an unverified fee model from the primary optimization. Sampling can still miss sub-5-second price changes. Mark all profits as **simulated**, never actual account returns.
- Show the **top five distinct settings combinations per 12/24/36-hour window**, ranked by net dollar profit after modeled fees. Show purchases, profitable purchases, spent, returned, ROI, tied settings and the $0 no-trade benchmark for each. Returned is cash received after exit fees, before subtracting entry spending; net profit subtracts that spending. Selecting historical winners does not validate future profitability.
- Equal-profit settings share a competition rank (1, 1, 3, etc.); disclose the total number tied, including undisplayed configurations. For display only, ties use ascending buy cap (OFF last), then take profit OFF before ascending percentages, then stop loss OFF before ascending percentages. This ordering does not imply a performance difference. Combinations with no purchases are excluded; no trading remains the separate $0 benchmark.

## Operation

The default branch workflow `.github/workflows/oracle-call-study-live.yml` runs five sequential five-hour segments and restarts daily. Its shared concurrency group replaces the former bounded run without allowing two recorders. Each segment resumes the saved data branch, validates calculations, and runs `collect.py --continuous --seconds 18000 --github --directory observations`. Public feeds only; no account or trading credentials.

The recorder samples every five seconds, checks settlements every fifteen seconds and publishes checkpoints about every minute. Every new session and newly verified result triggers an immediate recalculation. A separate process computes `reports/rolling.json` without blocking acquisition. It supplies per-round integer cash flows for the same complete buy-cap/TP/SL grid. The dashboard checks for new checkpoints every thirty seconds and uses a worker to recalculate exact rolling membership every second. The last five newly beneficial distinct settings from the rolling top-five rankings are retained with their identification time and original results. Repeated refreshes do not create duplicates. The all-time best setup (since study inception) is ranked across the full recorded history, with ties and exclusions disclosed. All-time results include older recorded sessions outside the rolling windows. The displayed source timestamps remain separate from the live window clock. Stale data and missing or excluded rounds remain visible.

Runner handoff gaps are measured; affected paths are excluded. Historical files stay on the data branch. Turning off the live workflow stops new observations; the page will flag stale source data.

`collect.py --seconds 30 --segment local --directory ./local-data` performs a bounded local smoke check. `analyze.py --data ./data-checkout` independently calculates the same grid for the current rolling window. `test_live.py` checks time boundaries and future-data exclusion; the Site's `test-rolling.mjs` checks the browser ranking against Python on saved real observations.
