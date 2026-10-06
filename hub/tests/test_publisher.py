import base64
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from hub.publisher import publish


class PublisherTests(unittest.TestCase):
    def test_catalog_commit_follows_asset_upload_and_keeps_app_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.fantome'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('WAD/Ahri.wad.client', b'fixture')
            item = {'id':'test', 'name':'Test', 'version':'1.0.0', 'champion':'Ahri',
                    'champion_id':103, 'description':'Fixture'}
            def response(data, status=200):
                r = Mock(ok=status<400, status_code=status)
                r.json.return_value = data
                return r
            session = Mock()
            session.__enter__ = Mock(return_value=session)
            session.__exit__ = Mock(return_value=False)
            session.get.side_effect = [response({},404), response({},404)]
            session.post.side_effect = [response({'id':2,'draft':True,'assets':[],
                'upload_url':'https://uploads.github.com/repos/okdev01/OKDEV/releases/2/assets{?name,label}'}), response({'name':'test-1.0.0.fantome'})]
            session.patch.return_value = response({})
            session.put.return_value = response({})
            with patch('hub.publisher.requests.Session', return_value=session):
                result = publish(path,item,'test-token')
            self.assertEqual(session.post.call_args_list[0].kwargs['json']['make_latest'],'false')
            self.assertTrue(session.patch.call_args.kwargs['json']['prerelease'])
            catalog = json.loads(base64.b64decode(session.put.call_args.kwargs['json']['content']))
            self.assertEqual(catalog['mods'][0]['sha256'],result['sha256'])
            self.assertNotIn('test-token',json.dumps(catalog))
