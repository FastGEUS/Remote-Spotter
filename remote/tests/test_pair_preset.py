import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from remote.desktop import config


class PairPresetTests(unittest.TestCase):
    def setUp(self):
        self.actual_preset_path=config.preset_path;self.actual_application_dir=config.application_dir
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.app=self.root/'Folder with spaces';self.app.mkdir()
        self.settings=self.root/'settings';self.presets=self.root/'presets';self.presets.mkdir()
        self.home=self.root/'home';self.home.mkdir()
        for role in ('pilot','viewer'):
            value={'schemaVersion':1,'role':role,'token':('p' if role=='pilot' else 'v')*64,
                   'ssh_key':'unused','host':'127.0.0.1','game':'auto'}
            (self.presets/(role+'.json')).write_text(json.dumps(value))
        for target,value in [('preset_path',lambda role:self.presets/(role+'.json')),('application_dir',lambda:self.app)]:
            mock=patch.object(config,target,value);mock.start();self.addCleanup(mock.stop)
        mock=patch.object(Path,'home',return_value=self.home);mock.start();self.addCleanup(mock.stop)
    def resolve(self,role='pilot'):
        with patch.object(config,'dpapi',lambda value,decrypt=False:value[::-1]):
            return config.load_startup_profile(role,self.settings)
    def save(self,profile):config.save_profile(profile,self.settings,protect=lambda value:value[::-1])
    def test_each_role_uses_its_own_token_and_key_beside_executable(self):
        key=self.app/'lmu_spotter';key.write_text('test-only-private-key')
        for role,token in [('pilot','p'*64),('viewer','v'*64)]:
            profile,personal=self.resolve(role)
            self.assertTrue(personal);self.assertEqual(profile.token,token)
            self.assertEqual(profile.ssh_key,str(key.resolve()))
    def test_directory_moves_override_stale_saved_paths_and_tokens(self):
        old=self.app/'old-key';old.touch()
        self.save(config.Profile('pilot','old-token-'*8,str(old),partner_name='Partner'))
        key=self.app/'lmu_spotter';key.touch()
        profile,_=self.resolve();self.assertEqual(profile.ssh_key,str(key));self.assertEqual(profile.token,'p'*64)
        self.assertEqual(profile.partner_name,'');self.save(profile)
        destination=self.root/'Moved';self.app.rename(destination);self.app=destination
        profile,_=self.resolve();self.assertEqual(profile.ssh_key,str(destination/'lmu_spotter'))
    def test_missing_sidecar_uses_saved_key_then_home_key(self):
        key=self.root/'saved-key';key.touch();self.save(config.Profile('pilot','p'*64,str(key)))
        self.assertEqual(self.resolve()[0].ssh_key,str(key))
        key.unlink();(self.home/'.ssh').mkdir();home_key=self.home/'.ssh/lmu_spotter';home_key.touch()
        self.assertEqual(self.resolve()[0].ssh_key,str(home_key))
    def test_legacy_names_in_saved_and_embedded_profiles_are_ignored(self):
        key=self.app/'lmu_spotter';key.touch()
        for role in ('pilot','viewer'):
            self.save(config.Profile(role,'old-token-'*8,str(key)))
            saved=self.settings/(role+'.json');value=json.loads(saved.read_text())
            value['partner_name']='Private saved name';saved.write_text(json.dumps(value))
            preset=self.presets/(role+'.json');value=json.loads(preset.read_text())
            value['partner_name']='Private embedded name';preset.write_text(json.dumps(value))
            profile,personal=self.resolve(role)
            self.assertTrue(personal);self.assertEqual(profile.partner_name,'')
            self.save(profile)
            self.assertNotIn('Private saved name',saved.read_text())
    def test_broken_dpapi_profile_does_not_force_token_setup(self):
        self.settings.mkdir();(self.settings/'pilot.json').write_text('not json')
        key=self.app/'lmu_spotter';key.touch()
        profile,personal=self.resolve();self.assertTrue(personal);self.assertEqual(profile.token,'p'*64)
    def test_no_key_returns_file_selection_target_not_missing_token(self):
        (self.app/'id_rsa').touch();(self.app/'lmu_spotter.pub').touch()
        profile,personal=self.resolve()
        self.assertTrue(personal);self.assertEqual(profile.ssh_key,str(self.app/'lmu_spotter'))
        self.assertFalse(Path(profile.ssh_key).exists());self.assertEqual(profile.token,'p'*64)
    def test_wrong_role_or_invalid_token_is_rejected(self):
        path=self.presets/'pilot.json';value=json.loads(path.read_text())
        value['role']='viewer';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.resolve()
        value['role']='pilot';value['token']='short';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.resolve()
    def test_frozen_app_uses_one_role_resource_and_executable_folder(self):
        internal=self.root/'bundle/_internal';(internal/'pair-preset').mkdir(parents=True)
        (internal/'pair-preset/pilot.json').write_bytes((self.presets/'pilot.json').read_bytes())
        exe=self.app/'SpotterPilot.exe';exe.touch();key=self.app/'lmu_spotter';key.touch()
        with patch.object(config.sys,'frozen',True,create=True),patch.object(config.sys,'_MEIPASS',str(internal),create=True),patch.object(config.sys,'executable',str(exe)):
            # Restore both real resource resolvers for the simulated frozen run.
            frozen_path=internal/'pair-preset/pilot.json'
            with patch.object(config,'preset_path',self.actual_preset_path),patch.object(config,'application_dir',self.actual_application_dir):
                profile,personal=self.resolve()
                self.assertTrue(personal);self.assertEqual(profile.token,'p'*64)
                self.assertEqual(profile.ssh_key,str(key))
                self.assertFalse((frozen_path.parent/'viewer.json').exists())
                self.assertIsNone(self.resolve('viewer')[0])
    def test_public_build_keeps_existing_protected_profile(self):
        (self.presets/'pilot.json').unlink();key=self.root/'user-key';key.touch()
        profile=config.Profile('pilot','user-token-'*6,str(key));self.save(profile)
        result,personal=self.resolve();self.assertFalse(personal);self.assertEqual(result,profile)
