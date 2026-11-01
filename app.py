"""Local Redis click-stream playground."""
import atexit
import json
import shlex
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from flask import Flask, Response, jsonify, request, send_file
from redis import Redis, RedisError
from redis.backoff import NoBackoff
from redis.retry import Retry
from traffic_metrics import HEADER, read_recent

ROOT = Path(__file__).resolve().parent
CONTROL_FILE = ROOT / '.simulation-control.json'
METRICS_FILE = ROOT / '.traffic-metrics.bin'
app = Flask(__name__)
lock = threading.RLock()
simulator = None
state = dict(running=False, paused=False, speed=120, message='Ready')


def client():
    return Redis.from_url(os.environ.get('REDIS_URL', 'redis://127.0.0.1:16379/0'),
                          decode_responses=True, socket_timeout=2, socket_connect_timeout=2)


def save_control():
    temporary = CONTROL_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(paused=state['paused'], speed=state['speed'])))
    temporary.replace(CONTROL_FILE)


def stop_simulator():
    global simulator
    if simulator is not None and simulator.poll() is None:
        simulator.terminate()
        try:
            simulator.wait(timeout=5)
        except subprocess.TimeoutExpired:
            simulator.kill()
            simulator.wait()
    simulator = None


atexit.register(stop_simulator)


def start_stack():
    global simulator
    if state['running']:
        return
    state.update(message='Starting Redis…', paused=False)
    save_control()
    subprocess.run(['docker', 'compose', 'up', '-d', '--wait'], cwd=ROOT, check=True, timeout=120)
    with client() as redis:
        redis.ping()
    METRICS_FILE.write_bytes(HEADER)
    log = open(ROOT / 'simulation.log', 'w')
    try:
        simulator = subprocess.Popen([sys.executable, '-u', 'run-sim.py'], cwd=ROOT,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     env={**os.environ, 'SIM_CONTROL_FILE': str(CONTROL_FILE),
                                          'SIM_METRICS_FILE': str(METRICS_FILE)})
    finally:
        log.close()
    state.update(running=True, message='Traffic is running')


def stop_stack():
    stop_simulator()
    subprocess.run(['docker', 'compose', 'stop'], cwd=ROOT, check=True, timeout=30)
    state.update(running=False, paused=False, message='Stopped')
    save_control()


@app.get('/')
def index():
    return send_file(ROOT / 'control-panel.html')


@app.get('/console')
def console():
    return send_file(ROOT / 'console.html')


@app.post('/api/command')
def command():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('command'), str):
        return jsonify(error='Enter a Redis command'), 400
    try:
        args = shlex.split(body['command'])
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if not args:
        return jsonify(error='Enter a Redis command'), 400
    # Requests use independent connections; conversational protocols need redis-cli.
    if args[0].upper() in {'MULTI', 'EXEC', 'DISCARD', 'WATCH', 'UNWATCH', 'SELECT',
                           'SUBSCRIBE', 'PSUBSCRIBE', 'SSUBSCRIBE', 'MONITOR', 'SYNC', 'PSYNC'}:
        return jsonify(error='Use redis-cli for connection-based commands; choose a database in the console selector.'), 400
    database = body.get('database', 0)
    if isinstance(database, bool) or not isinstance(database, int) or not 0 <= database <= 15:
        return jsonify(error='Database must be between 0 and 15'), 400
    started = time.monotonic()
    try:
        with Redis.from_url(os.environ.get('REDIS_URL', 'redis://127.0.0.1:16379/0'),
                            decode_responses=True, encoding_errors='backslashreplace',
                            socket_timeout=2, socket_connect_timeout=2,
                            retry=Retry(NoBackoff(), 0)) as redis:
            connection = redis.connection_pool.get_connection()
            try:
                connection.send_command('SELECT', database)
                connection.read_response()
                connection.send_command(*args)
                result = connection.read_response()
            finally:
                connection.disconnect()
                redis.connection_pool.release(connection)
        return jsonify(result=result, elapsed_ms=round((time.monotonic() - started) * 1000, 1))
    except RedisError as error:
        return jsonify(error=str(error)), 400


@app.get('/api/status')
def status():
    with lock:
        if state['running'] and simulator is not None and simulator.poll() is not None:
            state.update(running=False, paused=False,
                         message='Simulation finished' if simulator.returncode == 0 else
                         'Simulation failed; see simulation.log')
        return jsonify(state)


@app.get('/api/traffic')
def traffic_samples():
    return Response(read_recent(METRICS_FILE), mimetype='application/octet-stream',
                    headers={'Cache-Control': 'no-store'})


@app.get('/api/results')
def results():
    try:
        with client() as redis:
            leaders = redis.zrevrange('clicks:leaderboard', 0, 9, withscores=True)
            return jsonify(total=int(redis.get('clicks:total') or 0),
                           memory=redis.info('memory')['used_memory_human'],
                           leaders=[dict(video=video, clicks=int(score)) for video, score in leaders])
    except RedisError:
        return jsonify(error='Redis is unavailable'), 503


@app.post('/api/<action>')
def control(action):
    with lock:
        try:
            if action == 'start':
                start_stack()
            elif action == 'stop':
                stop_stack()
            elif action == 'restart':
                stop_stack()
                start_stack()
            elif action == 'traffic':
                body = request.get_json(silent=True) or {}
                if not isinstance(body, dict) or not isinstance(body.get('paused'), bool):
                    return jsonify(error='paused must be a boolean'), 400
                if not state['running']:
                    return jsonify(error='Start the simulation first'), 409
                state['paused'] = body['paused']
                state['message'] = 'Traffic is paused' if state['paused'] else 'Traffic is running'
                save_control()
            elif action == 'speed':
                body = request.get_json(silent=True) or {}
                value = body.get('speed') if isinstance(body, dict) else None
                if isinstance(value, bool) or value not in (1, 60, 120, 1000):
                    return jsonify(error='Speed must be 1, 60, 120, or 1000'), 400
                state['speed'] = value
                save_control()
            else:
                return jsonify(error='Unknown action'), 404
        except (OSError, subprocess.SubprocessError, RedisError) as error:
            stop_simulator()
            state.update(running=False, paused=False, message=f'Could not {action}: {error}')
            return jsonify(state), 500
        return status()


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False)
