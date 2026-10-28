// Generated from lib/stream-candles.ts; do not edit by hand.
const SETTLE_DELAY_MS = 2000, DEDUPE_WINDOW_MS = 120000, MAX_SEEN_TRADES = 50000;
// Only full buckets observed over an uninterrupted, sequenced connection qualify.
// The subscription snapshot contains recent trades, not a complete starting bucket.
export function createStreamCandles(intervalSeconds = 60, productId = 'BTC-USD') {
    if (![5, 15, 60].includes(intervalSeconds))
        throw new RangeError('Unsupported trade-candle interval.');
    if (typeof productId !== 'string' || !productId)
        throw new RangeError('A trade product is required.');
    const intervalMs = intervalSeconds * 1000;
    let sequence = null, safeStart = Infinity, watermark = 0, finalizedThrough = 0, generation = 0;
    const buckets = new Map();
    const seen = new Map(), finalizedIds = new Map();
    const nextBucket = (time) => (Math.floor(time / intervalMs) + 1) * intervalSeconds;
    function invalidate(time = Infinity) {
        generation++;
        safeStart = nextBucket(time);
        watermark = 0;
        finalizedThrough = 0;
        buckets.clear();
        seen.clear();
        finalizedIds.clear();
    }
    function reset() { sequence = null; invalidate(); }
    function pruneIds(through) {
        for (const [start, ids] of finalizedIds) {
            if ((start + intervalSeconds) * 1000 + DEDUPE_WINDOW_MS > through)
                continue;
            for (const id of ids)
                seen.delete(id);
            finalizedIds.delete(start);
        }
    }
    function ingest(message, now) {
        const seq = message?.sequence_num, stamp = Date.parse(message?.timestamp);
        if (!Number.isSafeInteger(seq) || seq < 0 || !Number.isFinite(stamp) || !Number.isFinite(now) || Math.abs(now - stamp) > 10000) {
            reset();
            return [];
        }
        if (sequence !== null && seq <= sequence)
            return [];
        const restartAt = Math.max(stamp, now);
        if (sequence === null)
            safeStart = nextBucket(restartAt);
        else if (seq !== sequence + 1)
            invalidate(restartAt);
        // Coinbase's sequence is global to this socket, including subscriptions and
        // heartbeats. They must advance it, but only trade updates seal trade buckets.
        sequence = seq;
        if (message.channel !== 'market_trades')
            return [];
        const events = message.events;
        if (!Array.isArray(events) || events.some((event) => !event || !['snapshot', 'update'].includes(event.type) || !Array.isArray(event.trades))) {
            invalidate(restartAt);
            return [];
        }
        if (events.some((event) => event.type === 'snapshot')) {
            invalidate(restartAt);
            return [];
        }
        pruneIds(Math.min(stamp, now));
        const trades = events.flatMap((event) => event.trades);
        for (const trade of trades) {
            if (!trade || typeof trade.product_id !== 'string') {
                invalidate(restartAt);
                return [];
            }
            if (trade.product_id !== productId)
                continue;
            const time = Date.parse(trade.time), price = Number(trade.price), size = Number(trade.size), rawId = String(trade.trade_id ?? '');
            if (!Number.isFinite(time) || !Number.isFinite(price) || price <= 0 || !Number.isFinite(size) || size <= 0 || !/^\d+$/.test(rawId) || time > stamp + 1000) {
                invalidate(restartAt);
                return [];
            }
            const start = Math.floor(time / intervalMs) * intervalSeconds, numericId = BigInt(rawId), id = numericId.toString(), previous = seen.get(id);
            if (previous) {
                if (previous.time !== time || previous.price !== price || previous.size !== size) {
                    invalidate(restartAt);
                    return [];
                }
                continue;
            }
            // Pre-start trades cannot make the first partial bucket complete. After a
            // reset, they also cannot contaminate the newly observed generation.
            if (start < safeStart)
                continue;
            // A genuinely new late trade makes previously emitted short history unsafe.
            // Consumers must clear usable short history whenever generation changes.
            if ((start + intervalSeconds) * 1000 <= finalizedThrough) {
                invalidate(restartAt);
                return [];
            }
            // Fail closed on capacity exhaustion rather than dropping dedupe records and
            // risking double-counted volume. Normal expiry removes completed-bucket IDs.
            if (seen.size >= MAX_SEEN_TRADES) {
                invalidate(restartAt);
                return [];
            }
            seen.set(id, { time, price, size });
            const bucket = buckets.get(start);
            if (!bucket) {
                buckets.set(start, { bar: { time: start, open: price, high: price, low: price, close: price, volume: size }, first: time, last: time, firstId: numericId, lastId: numericId, ids: new Set([id]) });
                continue;
            }
            if (!Number.isFinite(bucket.bar.volume + size)) {
                invalidate(restartAt);
                return [];
            }
            bucket.ids.add(id);
            bucket.bar.volume += size;
            bucket.bar.high = Math.max(bucket.bar.high, price);
            bucket.bar.low = Math.min(bucket.bar.low, price);
            if (time < bucket.first || (time === bucket.first && numericId < bucket.firstId)) {
                bucket.first = time;
                bucket.firstId = numericId;
                bucket.bar.open = price;
            }
            if (time > bucket.last || (time === bucket.last && numericId > bucket.lastId)) {
                bucket.last = time;
                bucket.lastId = numericId;
                bucket.bar.close = price;
            }
        }
        watermark = Math.max(watermark, stamp);
        const completed = [];
        for (const [start, bucket] of buckets) {
            const end = (start + intervalSeconds) * 1000;
            if (end + SETTLE_DELAY_MS <= Math.min(watermark, now)) {
                completed.push({ ...bucket.bar });
                buckets.delete(start);
                finalizedIds.set(start, bucket.ids);
                finalizedThrough = Math.max(finalizedThrough, end);
            }
        }
        return completed.sort((a, b) => a.time - b.time);
    }
    return { ingest, reset, get generation() { return generation; } };
}
