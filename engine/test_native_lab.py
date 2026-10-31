import unittest
from .native_lab import verify_response


class NativeProtocolTests(unittest.TestCase):
    def fixture(self):
        archive={'source_sha256':'a'*64,'output_sha256':'b'*64}
        response={'scope':'own_process_copied_wad','game_runtime_available':False,
                  'source_unchanged':True,'wide':True,'ansi':True,'memory_mapped':True,
                  'original_sha256':'a'*64,'redirected_sha256':'b'*64}
        return archive,response

    def test_expected_original_and_replacement_are_verified(self):
        archive,response=self.fixture()
        verify_response(response,archive)

    def test_game_claim_or_incorrect_content_is_rejected(self):
        changes=({'game_runtime_available':True},{'scope':'in_game'},
                 {'redirected_sha256':'c'*64},{'original_sha256':'c'*64},
                 {'source_unchanged':False},{'memory_mapped':False},
                 {'game_runtime_available':0})
        for change in changes:
            archive,response=self.fixture()
            response.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                verify_response(response,archive)


if __name__=='__main__':
    unittest.main()
