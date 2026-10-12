import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bot

class BotTests(unittest.TestCase):
    def test_weekdays(self):
        self.assertEqual(bot.status_for(date(2026,10,14)), 'open')
        self.assertEqual(bot.status_for(date(2026,10,17)), 'open')
        self.assertEqual(bot.status_for(date(2026,10,15)), 'closed')
        self.assertEqual(bot.status_for(date(2026,10,12)), 'closed')

    def test_fixed_tags_and_google(self):
        post = bot.caption(date(2026,10,14), 'open', 'instagram')
        self.assertIn('#麵処松もり', post)
        self.assertIn('11:00〜15:00', post)
        self.assertIn('10月14日（水曜日）', post)
        self.assertNotIn('#ラーメン', bot.caption(date(2026,10,14),'open','googlebusiness'))

    def test_override(self):
        with patch.object(Path,'read_text',return_value='{"2026-10-14":{"status":"closed"}}'):
            self.assertEqual(bot.status_for(date(2026,10,14)),'closed')

    def test_graphql_payload_uses_automatic_and_custom_time(self):
        data = []
        def fake_graphql(key, query, variables):
            data.append(variables['input'])
            return {'createPost':{'post':{'id':'demo', 'status':'buffer', 'dueAt':'2026-10-14T00:00:00.000Z'}}}
        with patch.object(bot,'graphql',side_effect=fake_graphql):
            for svc in bot.CHANNELS:
                bot.publish_one('unused','channel1',svc,'caption','2026-10-14T00:00:00.000Z','https://example.com/1.jpg')
        self.assertEqual(len(data),3)
        self.assertEqual(data[0]['mode'],'customScheduled')
        self.assertEqual(data[0]['schedulingType'],'automatic')
        self.assertEqual(data[1]['metadata']['instagram']['type'],'post')
        self.assertEqual(data[2]['metadata']['google']['type'],'whats_new')

if __name__ == '__main__':
    unittest.main()
