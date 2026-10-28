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
import zipfile
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

    def test_the_base_of_paths_travels_beside_the_converter(self):
        from tools.package_installers import BASE_NAME
        from retrorecomp.updater import BASE_ASSET
        self.assertEqual(BASE_NAME, BASE_ASSET)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'Retro-Recomp.exe'
            executable.write_bytes(b'MZauthored test converter')
            base = root / 'base.zip'
            with zipfile.ZipFile(base, 'w') as archive:
                archive.writestr('manifest.json', '{}')
            with patch('tools.package_installers.subprocess.run'):
                payload = payload_files(executable, '1.5.4', 'windows', base=base)
                self.assertEqual(payload[BASE_NAME], base.read_bytes())
                base.write_bytes(b'not an archive')
                with self.assertRaises(ValueError):
                    payload_files(executable, '1.5.4', 'windows', base=base)
        script = (ROOT / 'tools/installers/windows.iss').read_text(encoding='utf-8-sig')
        self.assertIn('Retro-Recomp-base.zip"; DestDir: "{app}"; Attribs: readonly; '
                      'Flags: overwritereadonly uninsremovereadonly', script)

    def test_debian_tree_runs_a_private_copy_per_user(self):
        from tools.package_installers import APP_ID, deb_tree
        files = {'Retro-Recomp': b'\x7fELF binary', 'Retro-Recomp.png': b'icon', 'LICENSE.txt': b'MIT',
                 'THIRD_PARTY_NOTICES.md': b'notices', 'INSTALL.txt': b'guide', 'uninstall.sh': b'unused',
                 'Retro-Recomp-base.zip': b'PK\x03\x04base'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'pkg'
            deb_tree(files, '1.4.1', root)
            listed = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
            self.assertEqual(listed, sorted([
                'DEBIAN/control', 'opt/retro-recomp/INSTALL.txt', 'opt/retro-recomp/LICENSE.txt',
                'opt/retro-recomp/Retro-Recomp', 'opt/retro-recomp/Retro-Recomp-base.zip',
                'opt/retro-recomp/Retro-Recomp.png',
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
            self.assertIn(b'Retro-Recomp-base.zip', launcher)
            if os.name != 'nt':
                self.assertEqual((root / 'opt/retro-recomp/Retro-Recomp-base.zip').stat().st_mode & 0o777, 0o444)
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
        # UTF-8 with a byte order mark: the uninstaller's messages are not ASCII.
        raw = (ROOT / 'tools/installers/windows.iss').read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        text = raw.decode('utf-8-sig')
        self.assertIn('PrivilegesRequired=lowest', text)
        self.assertNotIn('\n[UninstallDelete]', text)
        self.assertNotIn('recursesubdirs', text)
        self.assertNotIn('Source: "{#PayloadDir}\\*', text)

    def test_windows_uninstaller_offers_to_remove_only_the_tools_and_caches(self):
        text = (ROOT / 'tools/installers/windows.iss').read_bytes().decode('utf-8-sig')
        code = text[text.index('[Code]'):]
        # Asked (default No) in an interactive uninstall; a silent one needs /PURGETOOLS.
        self.assertIn('/PURGETOOLS', code)
        self.assertIn('(not UninstallSilent)', code)
        self.assertIn('MB_YESNO or MB_DEFBUTTON2, IDNO', code)
        # Exactly the three folders, below {app}; links are never followed.
        for folder in ("'\\datas\\tools'", "'\\.deps'", "'\\.build'"):
            self.assertIn(folder, code)
        self.assertIn('AttrReparsePoint', code)
        self.assertEqual(code.count('RemoveTree('), 3)       # declaration, recursion, one call
        self.assertNotIn('DelTree', code)
        # Every language the script declares has the three messages.
        languages = {line.split('"')[1] for line in text.splitlines() if line.startswith('Name: "') and 'MessagesFile' in line}
        for language in languages:
            for message in ('PurgeToolsQuestion', 'PurgeToolsQuestionNoSize', 'PurgeToolsRemoving', 'PurgeToolsMB', 'PurgeToolsGB'):
                self.assertIn(f'\n{language}.{message}=', text, (language, message))
        # The security notice (converted games are unsigned, antivirus false
        # positives) exists in every declared language and is added once to the finished page.
        for language in languages:
            self.assertIn(f'\n{language}.SecurityNotice=', text, language)
        self.assertIn("CustomMessage('SecurityNotice')", code)
        self.assertIn('wpFinished', code)


def find_bash():
    """A real bash: Git Bash on Windows (the WindowsApps stub is not one)."""
    if os.name == 'nt':
        for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'),
                     os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')):
            candidate = Path(base or '.') / 'Git/bin/bash.exe'
            if candidate.is_file():
                return str(candidate)
        return None
    return shutil.which('bash')


def make_link(link: Path, target: Path):
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        raise unittest.SkipTest('No symbolic links on this system.')


@unittest.skipUnless(find_bash(), 'Bash is needed to run the generated uninstaller')
class UninstallScriptTests(unittest.TestCase):
    """uninstall.sh on a temporary prefix: program files always go, games and
    settings always stay, the build tools and caches only on request."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rr-uninstall-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.prefix = self.root / 'App space' / 'Retro-Recomp'
        self.outside = self.root / 'outside'
        (self.outside / 'folder').mkdir(parents=True)
        (self.outside / 'folder/precious.txt').write_bytes(b'precious')
        self.managed = ['Retro-Recomp', 'Retro-Recomp.png', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md', 'INSTALL.txt']
        self.player = {'Games/Game Boy/Tetris/Tetris': b'game', 'datas/Retro-Recomp.json': b'preferences',
                       'datas/library/observations.json': b'discoveries', 'datas/BoxArt/gb/a.png': b'cover',
                       'My notes.txt': b'notes'}
        self.tools = {'datas/tools/llvm-mingw/bin/clang': b'x' * 3000, 'datas/tools/mingit/cmd/git': b'git',
                      '.deps/SDL/src/a.c': b'source', '.deps/SDL/checkout/objects/aa': b'read-only',
                      '.build/native-source/n.c': b'cache', '.build/gb_Tetris_0123456789ab_9150f87d/g.c': b'game'}

    def populate(self, tools=True):
        self.prefix.mkdir(parents=True, exist_ok=True)
        script = (ROOT / 'tools/installers/linux_uninstall.sh').read_bytes().replace(b'\r\n', b'\n')
        (self.prefix / 'uninstall.sh').write_bytes(script)
        (self.prefix / '.retro-recomp-install').write_bytes(b'Retro-Recomp per-user installation v1\n1.5.2\n\n')
        for name in self.managed:
            (self.prefix / name).write_bytes(b'managed')
        for name, raw in {**self.player, **(self.tools if tools else {})}.items():
            path = self.prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        if tools:
            (self.prefix / '.deps/SDL/checkout/objects/aa').chmod(0o444)

    def remove(self, path: Path):
        shutil.rmtree(path, onexc=lambda function, name, error: (os.chmod(name, 0o666), function(name)))

    def uninstall(self, *arguments, success=True):
        result = subprocess.run([find_bash(), (self.prefix / 'uninstall.sh').as_posix(), *arguments],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def assertPlayerKept(self):
        for name, raw in self.player.items():
            self.assertEqual((self.prefix / name).read_bytes(), raw, name)

    def test_without_the_option_everything_but_the_program_is_kept(self):
        self.populate()
        result = self.uninstall()        # no terminal: nothing is asked, tools stay
        for name in self.managed + ['uninstall.sh']:
            self.assertFalse((self.prefix / name).exists(), name)
        # The marker stays with the data, so a later reinstall recognises the folder.
        self.assertTrue((self.prefix / '.retro-recomp-install').exists())
        self.assertPlayerKept()
        for name, raw in self.tools.items():
            self.assertEqual((self.prefix / name).read_bytes(), raw, name)
        self.assertIn('build tools and compiler caches remain', result.stdout)

    def test_purge_removes_the_tools_and_caches_only(self):
        self.populate()
        make_link(self.prefix / '.deps/SDL/linked', self.outside / 'folder')
        make_link(self.prefix / '.build/linked', self.outside / 'folder')
        result = self.uninstall('--purge-tools')
        for name in ('datas/tools', '.deps', '.build'):
            self.assertFalse((self.prefix / name).exists(), name)
        self.assertPlayerKept()
        self.assertEqual((self.outside / 'folder/precious.txt').read_bytes(), b'precious')
        for name in self.managed + ['uninstall.sh']:
            self.assertFalse((self.prefix / name).exists(), name)
        self.assertIn('with its build tools and compiler caches', result.stdout)

    def test_purge_with_only_tools_leaves_no_folder_behind(self):
        self.populate(tools=True)
        for name in self.player:
            (self.prefix / name).unlink()
        shutil.rmtree(self.prefix / 'datas/library')
        shutil.rmtree(self.prefix / 'datas/BoxArt')
        shutil.rmtree(self.prefix / 'Games')
        (self.prefix / 'My notes.txt').unlink(missing_ok=True)
        self.uninstall('--purge-tools')
        self.assertFalse(self.prefix.exists())

    def test_a_link_in_place_of_a_folder_is_never_followed_or_removed(self):
        self.populate()
        self.remove(self.prefix / '.deps')
        make_link(self.prefix / '.deps', self.outside / 'folder')
        self.remove(self.prefix / 'datas/tools')
        elsewhere = self.root / 'elsewhere'
        (elsewhere / 'tools').mkdir(parents=True)
        (elsewhere / 'tools/t').write_bytes(b'tool')
        self.remove(self.prefix / 'datas')
        make_link(self.prefix / 'datas', elsewhere)
        self.uninstall('--purge-tools')
        self.assertTrue((self.prefix / '.deps').is_symlink())
        self.assertEqual((self.outside / 'folder/precious.txt').read_bytes(), b'precious')
        self.assertEqual((elsewhere / 'tools/t').read_bytes(), b'tool')
        self.assertFalse((self.prefix / '.build').exists())      # the real folder still went
        self.assertEqual((self.prefix / 'Games/Game Boy/Tetris/Tetris').read_bytes(), b'game')

    def test_unknown_option_is_refused_and_help_changes_nothing(self):
        self.populate()
        self.uninstall('--wipe', success=False)
        self.assertIn('--purge-tools', self.uninstall('--help').stdout)
        for name in self.managed:
            self.assertTrue((self.prefix / name).exists(), name)
        for name in self.tools:
            self.assertTrue((self.prefix / name).exists(), name)

    def ask(self, answer: bytes):
        """Run uninstall.sh in a terminal and type ``answer`` at its question."""
        import pty
        self.remove(self.prefix) if self.prefix.exists() else None
        self.populate()
        master, slave = pty.openpty()
        process = subprocess.Popen([find_bash(), (self.prefix / 'uninstall.sh').as_posix()],
                                   stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)
        output = b''
        while b'[y/N]' not in output:
            output += os.read(master, 4096)
        os.write(master, answer)
        try:
            while True:
                chunk = os.read(master, 4096)
                if not chunk:
                    break
                output += chunk
        except OSError:
            pass                      # the terminal closed with the script
        self.assertEqual(process.wait(timeout=60), 0, output)
        os.close(master)
        return output.decode(errors='replace')

    @unittest.skipUnless(os.name == 'posix', 'needs a pseudo-terminal')
    def test_a_terminal_session_is_asked_and_the_default_is_no(self):
        question = self.ask(b'\n')                   # just Enter: keep
        self.assertIn('Also remove the build tools and compiler caches (', question)
        self.assertIn('Your games, settings and discoveries are kept. [y/N]', question)
        self.assertTrue((self.prefix / '.deps/SDL/src/a.c').exists())
        self.assertFalse((self.prefix / 'Retro-Recomp').exists())
        self.assertPlayerKept()
        self.ask(b'y\n')
        for name in ('datas/tools', '.deps', '.build'):
            self.assertFalse((self.prefix / name).exists(), name)
        self.assertPlayerKept()


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
                 'THIRD_PARTY_NOTICES.md': b'notice', 'INSTALL.txt': b'guide',
                 'Retro-Recomp-base.zip': b'PK\x03\x04authored base'}
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
        base = self.prefix/'Retro-Recomp-base.zip'
        self.assertEqual(base.read_bytes(), b'PK\x03\x04authored base')
        self.assertEqual(base.stat().st_mode & 0o777, 0o444)   # read only, replaced by a reinstall above
        self.assertTrue(self.launcher.is_file())
        text=self.launcher.read_text()
        self.assertIn('%%',text)
        self.assertIn('X-RetroRecomp-InstallRoot=',text)
        subprocess.run(['bash',str(self.prefix/'uninstall.sh')],env=self.env,check=True,capture_output=True)
        self.assertFalse(self.launcher.exists())
        self.assertFalse((self.prefix/'Retro-Recomp').exists())
        self.assertFalse((self.prefix/'Retro-Recomp-base.zip').exists())
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
