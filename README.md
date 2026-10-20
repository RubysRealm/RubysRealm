# Oracle public-call paper study

This is a bounded, read-only observation and software-validation study. It places no orders and uses no Oracle or Kalshi account credentials. It records Oracle's public feed and public Kalshi books and settlements. It does not claim to reproduce Oracle's private order engine.

## Study protocol

- Record every 5 seconds, subject to response times and outages. Preserve acquisition times, errors, call revisions, quoted prices and displayed book depth.
- Use the first **observed locked** UP/DOWN call for a contract; never reconstruct missing calls from winners or aggregate accuracy. Preserve SITOUTs.
- Verify outcomes against Kalshi's finalized market result. Pending settlements stay pending.
- Start the study at the first full quarter-hour after collection begins; stop accepting rounds after 40 hours. Allow a settlement-only tail.
- Evaluate rolling 12/24/36-hour windows only when their full elapsed duration exists. Report missing rounds and exclude incomplete quote paths from the primary sample; do not describe an incomplete sample as the whole period.
- Paper entry: first usable Kalshi book observed within 15 seconds of the call's seal, on the called side. The first qualifying quote is the entry opportunity; a cap that rejects it skips that call (no hindsight waiting for a cheaper entry).
- Hypothetical stake: up to $1 of contracts per call, **whole contracts**, with entry fees additional. Cap quantity at displayed best-ask depth. Actual fills and the bot's sizing rules remain unverified.
- Buy caps: 1–99 cents in 1-cent steps, plus OFF. Actual quotes may be sub-cent; the cap itself is a whole-cent setting.
- TP: 0–100% gain in 1% steps, plus OFF. SL: 0–100% loss in 5% steps, plus OFF. Triggers are relative to the purchase price, before fees.
- A trigger executes at the **next sampled book**, walking the displayed bid levels. If the recorded depth cannot fill the entire position, wait for the next recorded book. Positions still open settle at the official result. This deliberately specified paper execution policy is not a verified reproduction of Oracle's implementation.
- Use the captured series fee type/multiplier, quadratic taker fees, six-decimal fee rounding and direct-member $0.0001 balance rounding. No settlement fee. Report the assumed fee basis.
- Reject contradictory calls, stale/slow entry data, gaps over 20 seconds after the entry opportunity, or an unverified fee model from the primary optimization. Sampling can still miss sub-5-second price changes. Mark all profits as **simulated**, never actual account returns.
- Show the **top five distinct settings combinations per 12/24/36-hour window**, ranked by net dollar profit after modeled fees. Show purchases, profitable purchases, spent, returned, ROI, tied settings and the $0 no-trade benchmark for each. Returned is cash received after exit fees, before subtracting entry spending; net profit subtracts that spending. Selecting historical winners does not validate future profitability.
- Equal-profit settings share a competition rank (1, 1, 3, etc.); disclose the total number tied, including undisplayed configurations. For display only, ties use ascending buy cap (OFF last), then take profit OFF before ascending percentages, then stop loss OFF before ascending percentages. This ordering does not imply a performance difference. Combinations with no purchases are excluded; no trading remains the separate $0 benchmark.

## Operation

The workflow lives on an isolated branch and is limited to eight sequential observation segments, each under GitHub's six-hour job limit. Checkpoints are written about every two minutes to the dedicated data branch, with no account data or secrets. Runner handoff gaps are measured and affected observations are excluded.

`collect.py --seconds 18000 --segment 1 --github` runs one hosted segment. `collect.py --seconds 30 --segment local --directory ./local-data` performs a local smoke check. `analyze.py --data ./data-checkout` runs the paper grid on downloaded observations. The workflow does not use any trading credentials.

Data endpoints, fee documents and run links are included in `state.json`/`status.json`. Never call a successful workflow launch proof that 36 hours were collected; verify the timestamps and coverage in the saved data.
