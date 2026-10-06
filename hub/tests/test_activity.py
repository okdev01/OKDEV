from unittest.mock import patch

from hub import activity, library
from hub.tests.test_library import LibraryFixture


class ActivityTests(LibraryFixture):
    def test_history_is_bounded_and_newest_first(self):
        for number in range(205):
            activity.record('selection', str(number), 2)
        events = activity.read()['events']
        self.assertEqual(len(events), 200)
        self.assertEqual(events[0]['name'], '204')
        self.assertEqual(events[-1]['name'], '5')
        self.assertEqual(len({event['id'] for event in events}), 200)

    def test_corrupt_history_never_overwrites_original(self):
        path = library.root() / 'activity.json'
        path.write_bytes(b'{broken\xff')
        activity.record('import', 'New mod')
        self.assertTrue(activity.read()['warning'])
        self.assertEqual(path.read_bytes(), b'{broken\xff')

    def test_disk_failure_does_not_fail_completed_operation(self):
        with patch('hub.library.write_json', side_effect=OSError('full')):
            activity.record('import', 'New mod')
        self.assertEqual(activity.read()['events'], [])

    def test_unknown_fields_are_not_exposed(self):
        activity.record('import', 'New mod')
        event = activity.read()['events'][0]
        library.write_json(library.root() / 'activity.json', [{**event, 'private': 'not public'}])
        self.assertEqual(activity.read()['events'], [event])

    def test_invalid_events_are_rejected(self):
        for kind, name, count in [('unknown', '', 1), ('import', None, 1),
                                  ('import', '', True), ('import', '', 2001)]:
            activity.record(kind, name, count)
        self.assertEqual(activity.read()['events'], [])

    def test_oversized_history_does_not_parse(self):
        (library.root() / 'activity.json').write_bytes(b' ' * (256 * 1024 + 1))
        with patch('hub.activity.json.loads') as parse:
            result = activity.read()
        parse.assert_not_called()
        self.assertTrue(result['warning'])
