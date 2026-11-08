from pathlib import Path
import sqlite3
import tempfile
import unittest

from kb.users import Users


class UserTests(unittest.TestCase):
    def test_login_role_update_and_logout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'users.sqlite'
            users = Users(path)
            users.create('oleg', 'long-test-password', 'lead')
            self.assertIsNone(users.login('oleg', 'wrong-password'))
            self.assertIsNone(users.login('unknown', 'wrong-password'))
            token = users.login('oleg', 'long-test-password')
            self.assertEqual(users.session(token), {'username': 'oleg', 'profile': 'lead'})
            with sqlite3.connect(path) as db:
                stored = db.execute('SELECT password FROM users').fetchone()[0]
                self.assertNotIn('password', stored)
                self.assertNotEqual(db.execute('SELECT token FROM sessions').fetchone()[0], token)
                db.execute("UPDATE users SET profile='support' WHERE username='oleg'")
            self.assertEqual(users.session(token)['profile'], 'support')
            users.logout(token)
            self.assertIsNone(users.session(token))
