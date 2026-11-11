"""Focused fail-closed generator tests; no game launch or generated-file writes.
Run with -B; --integration additionally reads the existing private ROM inputs.
"""
import argparse
import hashlib
import json
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_jimmie_visible_rails as g


class GeneratorTests(unittest.TestCase):
 def setUp(self):
  self.vertices = {'v':[(0,100,0),(100,100,0),(0,0,0)]}
  self.body = 'gsSPVertex(v, 3, 0), gsSP1Triangle(0, 1, 2, 0), gsSPEndDisplayList(),'

 def test_missing_list(self):
  with self.assertRaisesRegex(ValueError, 'unresolved alpha list'):
   g.display_triangles(['missing'], {}, {})

 def test_unknown_op(self):
  for op in ('gsSPMatrix', 'gsSPModifyVertex', 'gsSPUnknownGeometry'):
   with self.subTest(op=op), self.assertRaisesRegex(ValueError, 'unsupported display-list'):
    g.display_triangles(['a'], {'a':op+'(0),'}, {})

 def test_load_bounds(self):
  for count, base in ((4,0),(3,15),(0,0),(3,-1)):
   with self.subTest(count=count,base=base), self.assertRaisesRegex(ValueError, 'out-of-range'):
    g.display_triangles(['a'], {'a':f'gsSPVertex(v,{count},{base}),' }, self.vertices)

 def test_triangle_bounds(self):
  for index in (-1,3,16):
   with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'out-of-range'):
    g.display_triangles(['a'], {'a':f'gsSPVertex(v,3,0),gsSP1Triangle(0,1,{index},0),' }, self.vertices)

 def test_vertex_expression_refused(self):
  with self.assertRaisesRegex(ValueError, 'unresolved vertex expression'):
   g.display_triangles(['a'], {'a':'gsSPVertex(v + 1,2,0),' }, self.vertices)

 def test_nested_display(self):
  self.assertEqual(g.display_triangles(['a'], {'a':'gsSPDisplayList(b),', 'b':self.body}, self.vertices), [tuple(self.vertices['v'])])

 def test_branch_and_end_terminate(self):
  for prefix in ('gsSPBranchList(b),', 'gsSPEndDisplayList(),'):
   result=g.display_triangles(['a'], {'a':prefix+'gsSPUnknownGeometry(0),', 'b':self.body}, self.vertices)
   self.assertEqual(len(result), 1 if 'Branch' in prefix else 0)

 def test_recursion_refused(self):
  with self.assertRaisesRegex(ValueError, 'recursion'):
   g.display_triangles(['a'], {'a':'gsSPDisplayList(a),'}, {})

 def test_geo_transforms_refused(self):
  for op in ('SCALE','TRANSLATE_NODE','ROTATION_NODE','ANIMATED_PART','BILLBOARD'):
   geo='const GeoLayout root[] = { GEO_'+op+'(0,1), GEO_DISPLAY_LIST(LAYER_ALPHA,a), GEO_END(), };'
   with self.subTest(op=op), self.assertRaisesRegex(ValueError, 'unsupported geo command'):
    g.alpha_roots(geo,'root')

 def test_geo_missing_reference(self):
  with self.assertRaisesRegex(ValueError, 'unresolved geo layout'):
   g.alpha_roots('const GeoLayout root[] = { GEO_BRANCH(1,missing), GEO_END(), };','root')

 def test_geo_reachable_roots_only(self):
  geo='''const GeoLayout unused[] = { GEO_DISPLAY_LIST(LAYER_ALPHA,bad), GEO_END(), };
const GeoLayout root[] = { GEO_BRANCH(1,child), GEO_DISPLAY_LIST(LAYER_OPAQUE,opaque), GEO_END(), };
const GeoLayout child[] = { GEO_DISPLAY_LIST(LAYER_ALPHA,a), GEO_RETURN(), };'''
  self.assertEqual(g.alpha_roots(geo,'root'),['a'])

 def test_area_mapping(self):
  self.assertEqual(g.area_roots('AREA(/*index*/ 2, second), AREA(1, first), // AREA(3, fake)\n'),{2:'second',1:'first'})
  with self.assertRaisesRegex(ValueError, 'ambiguous area'):
   g.area_roots('AREA(1,a),AREA(1,b),')

 def test_level_mapping(self):
  source='DEFINE_LEVEL("Name", LEVEL_A, COURSE_A, folder_a, texture, 0)\nSTUB_LEVEL("", LEVEL_UNKNOWN, COURSE_NONE)'
  self.assertEqual(g.definitions(source),[('folder_a','LEVEL_A')])

 def test_us_conditionals(self):
  self.assertEqual(g.source_us('#ifdef VERSION_JP\njp\n#else\nus\n#endif'), 'us')
  self.assertEqual(g.source_us('#ifdef ENHANCE_LEVEL_TEXTURES\nenhanced\n#else\nbase\n#endif'), 'enhanced')
  with self.assertRaisesRegex(ValueError, 'unsupported preprocessor'):
   g.source_us('#ifdef UNKNOWN\nx\n#endif')


class PrivateIntegrationTests(unittest.TestCase):
 def test_baseline_segments_unchanged(self):
  baselines={'castle_inside':(34,'3768c308e60bcea647771fd68ef8d00d23656ade22eca63e066a042176b78c34'),
             'bob':(12,'90882c4b0abcbcd07e477abb1276bc829c2cfe1f60fcd390704682baae36cb8a')}
  for level,(count,digest) in baselines.items():
   with self.subTest(level=level):
    segments,receipt=g.extract(level)
    self.assertEqual(receipt['status'],'candidates')
    self.assertEqual(len(segments),count)
    self.assertEqual(hashlib.sha256(json.dumps(segments,separators=(',',':')).encode()).hexdigest(),digest)

 def test_scaled_area_excluded(self):
  segments,receipt=g.extract('thi',2)
  self.assertEqual(segments,[])
  self.assertEqual(receipt['status'],'excluded')
  self.assertIn('GEO_SCALE',receipt['warnings'][0])

 def test_all_areas_and_provenance(self):
  content,receipt=g.generate()
  self.assertEqual(len(receipt['areas']),len(list((g.ROOT/'levels').glob('*/areas/*/geo.inc.c'))))
  self.assertIn('levels/level_defines.h',receipt['source_sha256'])
  self.assertIn('NOT proven grindable',content)
  for key,area in receipt['areas'].items():
   level,number=key.split('/')
   self.assertIn(f'levels/{level}/areas/{number}/geo.inc.c',area['source_sha256'])
   self.assertIn(f'levels/{level}/script.c',area['source_sha256'])
   self.assertLessEqual(area['segments'],512)
   if area['status']=='excluded':
    self.assertEqual(area['segments'],0)
    self.assertTrue(area['warnings'])


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--integration',action='store_true')
 args=parser.parse_args()
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(GeneratorTests)
 if args.integration:
  suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PrivateIntegrationTests))
 raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
