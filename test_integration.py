"""Optional real-Redis smoke check, isolated from playground data in database 15."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from redis import Redis

ROOT = Path(__file__).resolve().parent


class IntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('RUN_REDIS_INTEGRATION') == '1', 'requires local Redis')
    def test_replay(self):
        redis = Redis(host='127.0.0.1', port=16379, db=15, decode_responses=True)
        self.assertEqual(redis.dbsize(), 0, 'Integration database 15 must be empty')
        keys = ['clicks:total', 'clicks:leaderboard', 'clicks:recent', 'clicks:minute:2026-09-23 00:00']
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)
                (path / 'youtube-clicks.csv').write_text(
                    'videoid,timestamp\nvid_0001,2026-09-23 00:00:00\n'
                    'vid_0002,2026-09-23 00:00:01\nvid_0001,2026-09-23 00:00:02\n')
                subprocess.run([sys.executable, str(ROOT / 'run-sim.py')], cwd=path,
                               env={**os.environ, 'REDIS_URL': 'redis://127.0.0.1:16379/15'},
                               check=True, timeout=10)
                self.assertEqual(redis.get('clicks:total'), '3')
                self.assertEqual(redis.zscore('clicks:leaderboard', 'vid_0001'), 2)
                self.assertEqual(redis.hget(keys[-1], 'vid_0001'), '2')
                self.assertGreater(redis.ttl(keys[-1]), 0)
                self.assertEqual(redis.xlen('clicks:recent'), 3)
                from traffic_metrics import read_recent, HEADER, RECORD
                data = read_recent(path / '.traffic-metrics.bin')[len(HEADER):]
                self.assertEqual(sum(row[3] for row in RECORD.iter_unpack(data)), 3)
        finally:
            redis.delete(*keys)
            redis.close()


if __name__ == '__main__':
    unittest.main()
