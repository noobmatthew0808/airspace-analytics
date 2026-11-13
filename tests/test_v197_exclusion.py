"""Presentation-only average exclusions; Aerodrome SQLite stays unchanged."""
import os
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from datetime import datetime,timedelta
from .make_sample_db import seed
from backend import data

class TestExclusion(unittest.TestCase):
    def test_exclusions_validated(self):
        self.assertEqual(data.excluded_dates_from_args("2026-11-09"),frozenset({"2026-11-09"}))
        for bad in ("2026-02-30","2026-11-09;DROP TABLE",",".join(["2026-11-09"]*65)):
            with self.assertRaises(data.DataError):data.excluded_dates_from_args(bad)

    def test_excluded_dates_not_in_averages_and_database_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"fictional.db";seed(path,12)
            previous=os.environ.get("AIRSPACE_DB");os.environ["AIRSPACE_DB"]=str(path)
            try:
                all_data=data.patterns({"period":"last_7d","metric":"observations"})
                self.assertTrue(any(x["samples"]>0 for x in all_data["weekday"]))
                with closing(data.connection()) as db:
                    count_before=db.execute("SELECT COUNT(*) FROM sightings_hourly").fetchone()[0]
                today=datetime.now(data.UK).date()
                excluded=",".join((today-timedelta(days=i)).isoformat() for i in range(9))
                reduced=data.patterns({"period":"last_7d","metric":"observations","exclude_days":excluded})
                self.assertTrue(all(x["samples"]==0 for x in reduced["weekday"]))
                self.assertTrue(all(x["samples"]==0 for x in reduced["hourly"]))
                with closing(data.connection()) as db:
                    count_after=db.execute("SELECT COUNT(*) FROM sightings_hourly").fetchone()[0]
                self.assertEqual(count_before,count_after)
                self.assertGreater(data.analyze({"period":"last_7d","metric":"observations","bucket":"day"})["total"],0)
            finally:
                if previous is None:os.environ.pop("AIRSPACE_DB",None)
                else:os.environ["AIRSPACE_DB"]=previous
