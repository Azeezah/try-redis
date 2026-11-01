"""Generate reproducible, timestamp-ordered clicks with popular videos and evening peaks."""
import csv
from datetime import datetime, timedelta
import math
import random


def generate(path='youtube-clicks.csv', count=100000, seed=42):
    rng = random.Random(seed)
    videos = [f'vid_{i:04d}' for i in range(1, 501)]
    weights = [1 / i ** 1.2 for i in range(1, 501)]
    seconds = []
    while len(seconds) < count:
        second = rng.randrange(86400)
        if rng.random() < 0.6 + 0.4 * math.cos(2 * math.pi * (second / 3600 - 20) / 24):
            seconds.append(second)
    start = datetime(2026, 9, 23)
    with open(path, 'w', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(['videoid', 'timestamp'])
        for video, second in zip(rng.choices(videos, weights=weights, k=count), sorted(seconds)):
            writer.writerow([video, (start + timedelta(seconds=second)).strftime('%Y-%m-%d %H:%M:%S')])


if __name__ == '__main__':
    generate()
    print('Created youtube-clicks.csv')
