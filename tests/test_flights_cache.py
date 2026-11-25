import unittest
from backend import flights_cache as c

class CacheTests(unittest.TestCase):
    def test_ground_evidence_survives_lost_transponder(self):
        now=1800000000
        ground=c._merge({}, {'status':'At LGW','at_airport':'LGW'},now)
        lost=c._merge(ground, {'status':'N/A'}, now+60)
        self.assertEqual(lost['at_airport'],'LGW')
        self.assertEqual(lost['last_landed_at'],now)
        self.assertEqual(c._public(lost,now+120)['at_airport'],'LGW')
        self.assertEqual(c._public(lost,now+c.AIRPORT_TTL+100)['status'],'N/A')

    def test_airborne_never_predicts_landing(self):
        now=1800000000
        flying=c._merge({}, {'status':'Flying LGW–BTS','route':'LGW–BTS'},now)
        self.assertEqual(c._public(flying,now+100)['status'],'N/A')
        self.assertEqual(c._merge(flying,{'status':'N/A'},now+35)['status'],'N/A')

    def test_new_live_flight_replaces_old_airport(self):
        now=1800000000
        ground=c._merge({}, {'status':'At LGW','at_airport':'LGW'},now)
        flying=c._merge(ground,{'status':'Flying','hex':'abc123'},now+35)
        self.assertEqual(c._public(flying,now+36)['status'],'Flying')
        self.assertFalse(flying.get('at_airport'))

    def test_registrations_deduplication(self):
        self.assertEqual(c._registrations([{'registration':'G-OLD (G-NEW)'},{'registration':'g-new'},{'registration':'No Reg'}]),['G-NEW'])

    def test_same_callsign_recovers_route_after_provider_changes(self):
        now=1800000000
        first=c._merge({}, {'status':'Flying LYS–LGW','callsign':'WUK123','route':'LYS–LGW','route_confidence':'usual'},now)
        gap=c._merge(first, {'status':'N/A'},now+35)
        current=c._merge(gap, {'status':'Flying','callsign':'WUK123'},now+70)
        self.assertEqual(current['route'],'LYS–LGW')
        self.assertNotIn('route',c._merge(current, {'status':'Flying','callsign':'WUK456'},now+105))
