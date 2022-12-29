#!/usr/bin/env python 

import json
from pathlib import Path
import datetime as dt
from shutil import copyfile, move
from pyexiv2 import Image
import progressbar
from sys import platform
import os
import sqlite3
import unicodedata
import re
import pyfiglet

SQLCIPHER_BIN = '/usr/local/bin/sqlcipher'

pyfiglet.print_figlet('Signal Bildexport', font='smscript')

predecrypt = False
if platform == 'win32':
    predecrypt = True
    signal_path = Path('~/AppData/Roaming/Signal').expanduser()

elif platform == 'darwin':
    signal_path = Path('~/Library/Application Support/Signal').expanduser()

elif platform == 'linux': # ie. WSL
    predecrypt = True
    parts = Path.cwd().parts
    userdir_parts = parts[0:parts.index('Users') + 2]
    userdir = Path(*userdir_parts)
    signal_path = userdir / 'AppData/Roaming/Signal'
    photos_path = userdir / 'Pictures/iCloud Photos/Photos'

else:
    raise NotImplementedError('Platform is not supported:', platform)

db_path_origin = signal_path / 'sql/db.sqlite'
config_path = signal_path / 'config.json'
attachments_path = signal_path / 'attachments.noindex'
previous_run = Path('previous_run')

db_path = Path.cwd() / 'db.sqlite'
copyfile(db_path_origin, db_path)

output_folder = Path.cwd() / 'out'
if not output_folder.exists(): output_folder.mkdir()
for f in output_folder.iterdir():
    f.unlink()

def tagify(value):
    return unicodedata.normalize('NFKD', value)

def slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value)
    return re.sub(r'[-\s]+', '-', value).strip('-_')

with open(config_path) as f:
    key = json.load(f)['key']

db_decrypted = Path.cwd() / 'db-decrypt.sqlite'
if predecrypt:
    print(f"Decrypting Signal DB...")
    if db_decrypted.exists():
        db_decrypted.unlink()
    command = (
        f'echo "'
        f"PRAGMA key = \\\"x'{key}'\\\";"
        f"ATTACH DATABASE '{db_decrypted}' AS plaintext KEY '';"
        f"SELECT sqlcipher_export('plaintext');"
        f"DETACH DATABASE plaintext;"
        f'" | {SQLCIPHER_BIN} {db_path}'
    )
    bar = progressbar.ProgressBar(max_value=progressbar.UnknownLength, redirect_stdout=True)
    bar.update()
    ret = os.system(command)
    bar.update()
    if ret != 0:
        raise RuntimeError('Could not decrypt DB')
    bar.finish()
    db = sqlite3.connect(str(db_decrypted))
    c = db.cursor()
else: 
    from pysqlcipher3 import dbapi2 as sqlcipher
    db = sqlcipher.connect(str(db_path))
    c = db.cursor()

    c.execute(f"PRAGMA KEY = \"x'{key}'\"")
    c.execute("PRAGMA cipher_page_size = 4096")
    c.execute("PRAGMA kdf_iter = 64000")
    c.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
    c.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")

previous_export_timestamp = 0
if previous_run.exists():
    with open(previous_run) as f:
        previous_export_timestamp = int(f.readline())

query = "SELECT m.json, u.name as user, u.profileFullName as userFallback, c.name as conversation, m.body as label, m.sent_at " \
+ "FROM messages m " \
+ "JOIN conversations u ON m.source = u.e164 " \
+ "JOIN conversations c ON m.conversationId = c.id " \
+ "WHERE m.hasVisualMediaAttachments = 1 AND m.type = 'incoming'" \
+ f"AND m.received_at > {previous_export_timestamp}" 

since = dt.datetime.fromtimestamp(previous_export_timestamp/1000).strftime('%Y-%m-%d')
print(f'Querying Signal DB for new images since {since}... ', end='', flush=True)
c.execute(query)
rows = c.fetchall()
print('done.')
print('Export and annotate images.')
most_recent_message = previous_export_timestamp

count_copied = 0
count_present = 0
for payload, user, user_fallback, conversation, label, timestamp in progressbar.progressbar(rows):
    most_recent_message = max(most_recent_message, timestamp)
    attachments = json.loads(payload)['attachments']
    if user is None: user = user_fallback
    for index, attachment in enumerate(attachments):
        if not 'path' in attachment:
            continue
        if attachment['contentType'] != 'image/jpeg':
            continue

        date = dt.datetime.fromtimestamp(timestamp/1000)
        filename = slugify(user) + '_' + date.strftime('%Y-%m-%d_%H%M%S')
        if len(attachments) > 1:
            filename += f'_{index + 1}'

        target = output_folder / (filename + '.jpg')

        if (photos_path / target.name).exists():
            count_present += 1
            continue

        copyfile(attachments_path / attachment['path'].replace('\\', '/'), target)
        count_copied += 1
        
        with Image(str(target)) as img:
            description = user
            if conversation != user:
                description += f' in "{conversation}"'
            if label:
                description += f': {label}'

            exif = img.read_exif()
            iptc = img.read_iptc()
            exif['Exif.Photo.DateTimeOriginal'] = date.strftime('%Y:%m:%d %H:%M:%S')
            exif['Exif.Image.Model'] = 'Signal Export'
            exif['Exif.Image.Artist'] = user
            exif['Exif.Image.ImageDescription'] = description
            tags = user, 'Signal'
            if conversation != user:
                tags += tagify(conversation),
            iptc['Iptc.Application2.Keywords'] = tags
            img.modify_iptc(iptc)
            img.modify_exif(exif)
            move(target, photos_path)

db_path.unlink()
db_decrypted.unlink()

with open(previous_run, 'w') as f:
    f.write(str(most_recent_message))

print(f'New images since {since}: {count_copied}')
print(f'Images already in iCloud folder: {count_present}')
print('Press enter to close.')
input()