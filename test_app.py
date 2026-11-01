import unittest
from unittest.mock import patch
import app


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_invalid_controls(self):
        for value in (None, True, 0, 500, '120', []):
            self.assertEqual(self.client.post('/api/speed', json={'speed': value}).status_code, 400)
        self.assertEqual(self.client.post('/api/traffic', json={'paused': 'false'}).status_code, 400)

    def test_start_failure_is_visible(self):
        with patch.object(app, 'start_stack', side_effect=OSError('Docker unavailable')):
            response = self.client.post('/api/start')
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json['running'])
        self.assertIn('Docker unavailable', response.json['message'])

    def test_results_unavailable(self):
        with patch.object(app, 'client', side_effect=app.RedisError('offline')):
            self.assertEqual(self.client.get('/api/results').status_code, 503)

    def test_command_validation(self):
        for body in ({}, {'command': ''}, {'command': 'SET "unfinished'},
                     {'command': 'PING', 'database': True}, {'command': 'MULTI'}):
            self.assertEqual(self.client.post('/api/command', json=body).status_code, 400)

    def test_raw_command_and_quoted_arguments(self):
        with patch.object(app.Redis, 'from_url') as factory:
            redis = factory.return_value.__enter__.return_value
            connection = redis.connection_pool.get_connection.return_value
            connection.read_response.side_effect = ['OK', 'OK']
            response = self.client.post('/api/command', json={'command': 'SET greeting "hello world"'})
            self.assertEqual(response.json['result'], 'OK')
            connection.send_command.assert_any_call('SET', 'greeting', 'hello world')
            connection.disconnect.assert_called_once()

    def test_redis_error_is_displayed(self):
        with patch.object(app.Redis, 'from_url', side_effect=app.RedisError('wrong number of arguments')):
            response = self.client.post('/api/command', json={'command': 'GET'})
            self.assertEqual(response.status_code, 400)
            self.assertIn('wrong number', response.json['error'])

    def test_console_page(self):
        response = self.client.get('/console')
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_panel(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        response.close()


if __name__ == '__main__':
    unittest.main()
