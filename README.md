# Redis playground

Try Redis with the same video-click workload and controls as `try-flink`.
Replay 100,000 clicks over a simulated day, change the speed, pause traffic,
and watch delivery rates and the top ten videos update live.

## Setup and run

Install and open Docker Desktop, then:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open http://localhost:5001 and press play. This starts Redis in Docker and
replays the included `youtube-clicks.csv`. Play toggles pause/resume once running.
Stop stops the simulation and Redis; restart replays the file from the beginning.
Speed options are 1×, 60×, 120×, and 1000×. At 120× a day takes about 12 minutes,
subject to how quickly your laptop can deliver the clicks.

Redis uses port **16379**, so this can run alongside `try-flink` and a Redis
installation using the default port. All exposed services bind to localhost.

## What Redis stores

Each click sends a Redis transaction containing:

- `XADD clicks:recent`: a stream of roughly the latest 10,000 events.
- `ZINCRBY clicks:leaderboard`: total clicks per video, ranked by popularity.
- `HINCRBY clicks:minute:2026-09-23 20:00`: clicks per video per simulated minute.
- `EXPIRE` on each minute bucket: retained for 24 hours of real time after its latest write.
- `INCR clicks:total`: total acknowledged clicks across runs.

The traffic chart shows expected, attempted, and acknowledged **clicks per real
second**, not Redis commands per second (each click issues five commands plus
transaction overhead). No automatic retries are used for click writes because
a lost response could otherwise double-count a click. A failed write stops the
simulation; inspect `simulation.log`. Acknowledged means Redis replied, not that
an individual write has been synchronously flushed to disk.

Data persists in a Docker volume with append-only persistence. Restart adds to
existing counts; it does not clear them. Memory is capped at 256 MB with
`noeviction`, so Redis rejects writes if full instead of silently dropping counters.
The stream is capped approximately; the leaderboard is bounded by the dataset's
500 videos, while minute buckets expire.

## Run manually and inspect

```sh
docker compose up -d --wait
.venv/bin/python run-sim.py

docker compose exec redis redis-cli GET clicks:total
docker compose exec redis redis-cli ZREVRANGE clicks:leaderboard 0 9 WITHSCORES
docker compose exec redis redis-cli XREVRANGE clicks:recent + - COUNT 5
docker compose exec redis redis-cli HGETALL 'clicks:minute:2026-09-23 20:00'
docker compose exec redis redis-cli INFO memory
docker compose exec redis redis-cli INFO stats
```

Regenerate a deterministic dataset using `.venv/bin/python generate-fake-clicks-data.py`.
The manual simulator honors `.simulation-control.json` left by the panel;
delete that file to return to the default running state and 120× speed.
`REDIS_URL` overrides the client's connection (the panel still manages local Docker).
Closing the panel's Python server stops its worker but leaves Redis available;
use `docker compose stop` when done.

To intentionally erase this playground's stored clicks, stop the panel and run:

```sh
docker compose down -v
```

## Checks

```sh
.venv/bin/python -m unittest test_traffic_metrics test_simulation_clock test_app
node test_traffic_chart.cjs
```

The binary traffic format, chart, and continuous pause/speed clock are adapted
from the neighboring `try-flink` project. Redis aggregation uses the official
[redis-py transaction API](https://redis.io/docs/latest/develop/clients/redis-py/transpipe/).

Optional real-Redis smoke check (requires an empty database 15 on this local Redis):

```sh
RUN_REDIS_INTEGRATION=1 .venv/bin/python -m unittest test_integration
```

This project retains the GPL-3.0 license from `try-flink`; see `LICENSE`.
