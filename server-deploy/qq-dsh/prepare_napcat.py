"""Prepare private NapCat files without starting Docker, QQ, or the chat bridge."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import zipfile

BASE = Path('/home/ubuntu/qq-dsh')
RUNTIME = BASE / 'napcat-runtime'
ZIP = Path('/home/ubuntu/qq-codex/inspection/NapCat.Shell.zip')
EXPECTED = '02e5ff0f79916c1e04c81c1b4590056406fb4293f1f1300c955e71fd08b2829d'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def main():
    os.umask(0o077)
    if hashlib.sha256(ZIP.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError('NapCat ZIP checksum mismatch')
    app = RUNTIME / 'app'
    package = app / 'napcat'
    private = RUNTIME / '.private'
    private.mkdir(parents=True, mode=0o700, exist_ok=True)
    package.mkdir(parents=True, mode=0o700, exist_ok=True)
    marker = private / 'prepared.json'
    if marker.exists():
        raise RuntimeError('Already prepared; refusing to overwrite private configuration')
    with zipfile.ZipFile(ZIP) as archive:
        for info in archive.infolist():
            target = (package / info.filename).resolve()
            if not target.is_relative_to(package.resolve()) or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Unsafe ZIP path')
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC check failed')
        archive.extractall(package)
    for relative in ('qq-data', 'app/.config/QQ', 'app/.cache', 'app/napcat/cache',
                     'app/napcat/logs', 'app/napcat/plugins'):
        (RUNTIME / relative).mkdir(parents=True, mode=0o700, exist_ok=True)
    config = package / 'config'
    onebot_token = secrets.token_urlsafe(36)
    webui_token = secrets.token_urlsafe(36)
    onebot = {'network': {'httpSseServers': [{
        'name': 'codex-private', 'enable': True, 'host': '0.0.0.0', 'port': 3000,
        'enableCors': False, 'enableWebsocket': False, 'messagePostFormat': 'array',
        'token': onebot_token, 'debug': False, 'reportSelfMessage': False,
    }]}, 'musicSignUrl': '', 'enableLocalFile2Url': False, 'parseMultMsg': False,
        'imageDownloadProxy': ''}
    for name in ('onebot11.json', 'onebot11_2223525305.json'):
        write_json(config / name, onebot)
    write_json(config / 'webui.json', {'host': '0.0.0.0', 'port': 6099,
               'prefix': '', 'token': webui_token, 'loginRate': 3})
    write_json(private / 'bridge-config.json', {
        'owner_qq': '17162047', 'bot_qq': '2223525305',
        'onebot_url': 'http://127.0.0.1:13101', 'onebot_token': onebot_token,
    })
    shutil.copyfile(BASE / 'container-start.sh', app / 'container-start.sh')
    (app / 'container-start.sh').chmod(0o500)
    write_json(marker, {'napcat_version': '4.18.42', 'zip_sha256': EXPECTED,
                       'bot_qq': '2223525305', 'owner_qq': '17162047'})
    print('Prepared private configuration; no service has been started.')


if __name__ == '__main__':
    main()
