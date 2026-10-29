import gzip
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from import_prefecture import kami_groups,published,office

class NationwideCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((ROOT/'data/catalog.json').read_text())
        cls.regions=[r for r in cls.catalog['regions']if r['status']=='ready']
    def test_registry_covers_47_unique_codes_and_exact_ready_totals(self):
        self.assertEqual({r['code']for r in self.catalog['regions']},set(range(1,48)))
        self.assertEqual(self.catalog['totals']['records'],sum(r['records']for r in self.regions))
        self.assertEqual(self.catalog['totals']['regions'],len(self.regions))
        for region in self.regions:
            rows=[r for p in region['collections']for r in json.loads((ROOT/p).read_text())]
            self.assertEqual(len(rows),region['records'])
            self.assertEqual(len({r['id']for r in rows}),len(rows))
            self.assertTrue(all(r['prefecture_code']==region['code']for r in rows))
            self.assertTrue((ROOT/region['offline']).is_file())
    def test_source_role_markers_and_unknown_values_do_not_become_invented_deities(self):
        groups=kami_groups('《合》倉稲魂命、《主》大山祇命、《配》木花咲耶姫命',0,True)
        self.assertEqual([g['names']for g in groups],[['倉稲魂命'],['大山祇命'],['木花咲耶姫命']])
        self.assertTrue(all('历史' in g['role']for g in groups))
        self.assertFalse(published('不詳'))
        self.assertFalse(published('不祥'))
        self.assertTrue(office('千葉県神社庁'))
        self.assertFalse(office('北海道神宮'))
    def test_history_and_viewport_coordinates_are_never_plotted_as_shrine_points(self):
        for region in self.regions:
            if region['code']==31:continue
            for path in region['collections']:
                for r in json.loads((ROOT/path).read_text()):
                    if r['record_status']=='historical_directory':
                        self.assertTrue(all(l['map_status']!='mapped'for l in r['locations']))
                        self.assertIn('历史',r['headline'])
                    if r.get('provenance',{}).get('coordinate_kind')=='published_map_viewport':
                        self.assertTrue(all(l['map_status']=='source_map_viewport'for l in r['locations']))
                    self.assertFalse(office(r['name']))
                    for group in r['kami']:
                        self.assertTrue(group['sources'])
                        self.assertTrue(all(0<=n<len(r['sources'])for n in group['sources']))
    def test_packaged_sqlite_is_a_real_valid_database_with_all_region_records(self):
        with tempfile.TemporaryDirectory()as folder:
            for region in self.regions:
                raw=(ROOT/region['database']).read_bytes()
                if region['database'].endswith('.gz'):raw=gzip.decompress(raw)
                self.assertTrue(raw.startswith(b'SQLite format 3\0'))
                path=Path(folder)/'catalog.sqlite';path.write_bytes(raw)
                with sqlite3.connect(path)as db:
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                    self.assertEqual(db.execute('SELECT count(*) FROM shrines').fetchone()[0],region['records'])
    def test_tottori_retains_original_research_ids_and_two_ogamiyama_locations(self):
        bird=next(r for r in self.regions if r['code']==31)
        rows=[r for p in bird['collections']for r in json.loads((ROOT/p).read_text())]
        by={r['id']:r for r in rows}
        self.assertEqual(len(rows),824)
        self.assertEqual(len(by['ogamiyama']['locations']),2)
        self.assertEqual(len(by['akaiiwa']['kami']),2)
        self.assertEqual(sum(r['record_status']=='research_enriched'for r in rows),12)

if __name__=='__main__':unittest.main()
