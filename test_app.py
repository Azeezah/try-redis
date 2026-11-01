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

    def test_panel(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        response.close()


if __name__ == '__main__':
    unittest.main()
