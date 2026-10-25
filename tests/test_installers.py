"""Installer contents and ownership/data-preservation checks, without any ROMs."""
from pathlib import Path
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools.package_installers import ROOT, linux_archive, payload_files


class InstallerPayloadTests(unittest.TestCase):
    def test_payload_does_not_collect_neighboring_private_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'Retro-Recomp.exe'
            executable.write_bytes(b'MZauthored test converter')
            (root / 'private.rom').write_bytes(b'private fixture')
            (root / 'datas').mkdir()
            (root / 'datas/favorites.json').write_text('private fixture')
            with patch('tools.package_installers.subprocess.run') as probe:
                payload = payload_files(executable, '1.1.5', 'windows')
            self.assertEqual(set(payload), {'Retro-Recomp.exe', 'Retro-Recomp.ico',
                             'LICENSE.txt', 'THIRD_PARTY_NOTICES.md', 'INSTALL.txt', 'RELEASE_NOTES.txt'})
            self.assertIn(b'releases/tag/v1.1.5', payload['RELEASE_NOTES.txt'])
            self.assertEqual(payload['Retro-Recomp.exe'], executable.read_bytes())
            self.assertEqual(probe.call_args.args[0][1:], ['_verify-update', '1.1.5'])

    def test_debian_tree_runs_a_private_copy_per_user(self):
        from tools.package_installers import APP_ID, deb_tree
        files = {'Retro-Recomp': b'\x7fELF binary', 'Retro-Recomp.png': b'icon', 'LICENSE.txt': b'MIT',
                 'THIRD_PARTY_NOTICES.md': b'notices', 'INSTALL.txt': b'guide', 'uninstall.sh': b'unused'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'pkg'
            deb_tree(files, '1.4.1', root)
            listed = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
            self.assertEqual(listed, sorted([
                'DEBIAN/control', 'opt/retro-recomp/INSTALL.txt', 'opt/retro-recomp/LICENSE.txt',
                'opt/retro-recomp/Retro-Recomp', 'opt/retro-recomp/Retro-Recomp.png',
                'opt/retro-recomp/THIRD_PARTY_NOTICES.md', 'opt/retro-recomp/VERSION', 'usr/bin/retro-recomp',
                f'usr/share/applications/{APP_ID}.desktop', 'usr/share/doc/retro-recomp/copyright',
                f'usr/share/icons/hicolor/256x256/apps/{APP_ID}.png']))
            control = (root / 'DEBIAN/control').read_text()
            self.assertIn('Package: retro-recomp\nVersion: 1.4.1\nArchitecture: amd64', control)
            self.assertIn('Depends: libc6 (>= 2.41)', control)
            entry = (root / f'usr/share/applications/{APP_ID}.desktop').read_text()
            self.assertIn('Exec=retro-recomp', entry)
            # The desktop shows its starting cursor until the window, of
            # Tk class Retro-Recomp, appears.
            self.assertIn('StartupNotify=true\nStartupWMClass=Retro-Recomp', entry)
            launcher = (root / 'usr/bin/retro-recomp').read_bytes()
            self.assertNotIn(b'\r\n', launcher)
            self.assertIn(b'.local/opt/Retro-Recomp', launcher)
            self.assertIn(b'PYINSTALLER_SUPPRESS_SPLASH_SCREEN', launcher)
            self.assertEqual((root / 'opt/retro-recomp/VERSION').read_text(), '1.4.1\n')

    def test_reproducible_linux_payload_contains_only_plain_files(self):
        files = {'Retro-Recomp': b'authored binary', 'uninstall.sh': b'authored uninstaller', 'INSTALL.txt': b'guide'}
        first = linux_archive(files)
        self.assertEqual(first, linux_archive(dict(reversed(list(files.items())))))
        with tarfile.open(fileobj=io.BytesIO(first), mode='r:gz') as tar:
            self.assertEqual(set(tar.getnames()), set(files))
            for member in tar:
                self.assertTrue(member.isfile())
                self.assertEqual(member.uid, 0)
                self.assertEqual(member.mtime, 0)
                self.assertEqual(tar.extractfile(member).read(), files[member.name])

    def test_windows_installer_preserves_untracked_data(self):
        text = (ROOT / 'tools/installers/windows.iss').read_text()
        self.assertIn('PrivilegesRequired=lowest', text)
        self.assertNotIn('\n[UninstallDelete]', text)
        self.assertNotIn('recursesubdirs', text)
        self.assertNotIn('Source: "{#PayloadDir}\\*', text)


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() != 0 and shutil.which('bash'),
                     'Bash integration test runs as an ordinary Linux user')
class LinuxInstallLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rr-installer-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        # Test shell behavior on Ubuntu CI as well as Debian. This fixture is
        # a shell probe, not a claim about native support on older glibc.
        libc = self.tools / 'getconf'
        libc.write_text('#!/bin/sh\necho "glibc 2.41"\n')
        libc.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_DATA_HOME=str(self.home/'menu'), PATH=str(self.tools)+':'+os.environ['PATH'])
        self.prefix = self.home / 'App space % & $ " /Retro-Recomp'
        self.launcher = self.home / 'menu/applications/io.github.ArthurReboulSalze.RetroRecomp.desktop'
        self.package = self.root / 'installer.run'
        files = {'Retro-Recomp': b'#!/bin/sh\n[ "$1" = _verify-update ] && [ "$2" = 1.1.5 ]\n',
                 'uninstall.sh': (ROOT/'tools/installers/linux_uninstall.sh').read_bytes(),
                 'Retro-Recomp.png': b'authored icon', 'LICENSE.txt': b'license',
                 'THIRD_PARTY_NOTICES.md': b'notice', 'INSTALL.txt': b'guide'}
        archive = linux_archive(files)
        header = (ROOT/'tools/installers/linux_install.sh').read_text().replace('@VERSION@','1.1.5').replace(
            '@PAYLOAD_SHA256@',hashlib.sha256(archive).hexdigest())
        self.package.write_bytes(header.encode()+archive)

    def install(self, success=True):
        result = subprocess.run(['bash',str(self.package),'--yes','--prefix',str(self.prefix)],
                                env=self.env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode == 0, success, result.stdout+result.stderr)
        return result

    def test_install_reinstall_and_uninstall_keep_all_user_data(self):
        self.install()
        saved = {'datas/Retro-Recomp.json': b'preferences', 'datas/library/observations': b'observations',
                 'Games/Master System/example': b'game', '.deps/tool': b'compiler', '.build/cache': b'cache'}
        for name, raw in saved.items():
            path = self.prefix/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
        self.install()
        self.assertTrue(self.launcher.is_file())
        text=self.launcher.read_text()
        self.assertIn('%%',text)
        self.assertIn('X-RetroRecomp-InstallRoot=',text)
        subprocess.run(['bash',str(self.prefix/'uninstall.sh')],env=self.env,check=True,capture_output=True)
        self.assertFalse(self.launcher.exists())
        self.assertFalse((self.prefix/'Retro-Recomp').exists())
        for name,raw in saved.items():
            self.assertEqual((self.prefix/name).read_bytes(),raw)
        self.install()
        self.assertTrue(self.launcher.is_file())
        for name,raw in saved.items():
            self.assertEqual((self.prefix/name).read_bytes(),raw)

    def test_unowned_directory_and_foreign_launcher_are_not_overwritten(self):
        self.prefix.mkdir(parents=True)
        (self.prefix/'keep.txt').write_bytes(b'keep')
        self.install(False)
        self.assertEqual((self.prefix/'keep.txt').read_bytes(),b'keep')
        self.prefix = self.home/'another-install'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text('[Desktop Entry]\nName=Another application\n')
        self.install(False)
        self.assertIn('Another application',self.launcher.read_text())

    def test_corrupt_payload_never_replaces_installed_converter(self):
        self.install()
        original=(self.prefix/'Retro-Recomp').read_bytes()
        raw=self.package.read_bytes()
        self.package.write_bytes(raw[:-10]+b'corruption')
        self.install(False)
        self.assertEqual((self.prefix/'Retro-Recomp').read_bytes(),original)
        self.assertFalse(list(self.prefix.glob('.RetroRecomp-install-*')))

    def test_symbolic_link_cannot_redirect_a_managed_file(self):
        self.install()
        outside=self.home/'precious'
        outside.write_bytes(b'precious')
        target=self.prefix/'LICENSE.txt'
        target.unlink()
        target.symlink_to(outside)
        self.install(False)
        self.assertEqual(outside.read_bytes(),b'precious')


if __name__ == '__main__':
    unittest.main()
