import json
import tempfile
import unittest
from pathlib import Path
from remote.profile import load_profile,clean_token,validate_url


class ProfileTests(unittest.TestCase):
    def test_saved_profile_loads_bom_and_local_tunnel(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json'
            path.write_text(json.dumps({'pilotToken':'a'*64,'url':'ws://127.0.0.1:8080/ws/pilot'}),encoding='utf-8-sig')
            result=load_profile(path)
            self.assertEqual(result['token'],'a'*64)
            self.assertTrue(result['allow_insecure_local'])

    def test_profile_missing_falls_back_to_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(load_profile(Path(directory)/'absent.json'))

    def test_copy_artifacts_at_edges_are_removed(self):
        self.assertEqual(clean_token(' \ufeff'+'a'*64+'\u200b\n'),'a'*64)
        self.assertEqual(clean_token('"'+'a'*64+'"'),'a'*64)

    def test_bad_key_error_does_not_echo_input(self):
        for value in ('private short secret','a'*31,'a'*32+'\n'+'b'*32,'Ж'*64,123):
            with self.assertRaises(ValueError) as caught:clean_token(value)
            self.assertNotIn(str(value),str(caught.exception))

    def test_profile_cannot_silently_send_key_over_public_plaintext(self):
        for url in ('ws://127.0.0.1:8080/ws/pilot','ws://127.0.0.1.evil:8080/ws/pilot',
                    'wss://example.com/ws/view','wss://example.com/ws/pilot?token=x'):
            with self.assertRaises(ValueError):validate_url(url)
        self.assertEqual(validate_url('wss://example.com/ws/pilot'),('wss://example.com/ws/pilot',False))


if __name__=='__main__':unittest.main()
