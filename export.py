#!/usr/bin/env python
import json
from pathlib import Path
import datetime as dt
from shutil import copyfile, move

from exiftool.exceptions import ExifToolExecuteError

from files import decrypt_attachment

import keyring
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from exiftool import ExifToolHelper

import progressbar
import os
import sqlite3
import unicodedata
import re
import pyfiglet
from sys import platform

import config

first_run = config.load()

pyfiglet.print_figlet('Signal Bildexport', font='smscript')
print(flush=True)

signal_path = Path(config.get('x-advanced.signal_path'))
win_icloud_photos_path = Path(config.get('output_path'))

db_path = signal_path / 'sql/db.sqlite'
attachments_path = signal_path / 'attachments.noindex'

if config.get('x-advanced.pre_copy'):
    db_path_ = Path('db.sqlite')
    copyfile(db_path, db_path_)
    db_path = db_path_

tmp_folder = Path('tmp')
if not tmp_folder.exists(): tmp_folder.mkdir()
for f in tmp_folder.iterdir():
    f.unlink()


def tagify(value):
    return unicodedata.normalize('NFKD', value).replace(',', '')


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


with open(signal_path / 'config.json') as f:
    modern_key = json.load(f)['encryptedKey']

encrypted = bytes.fromhex(modern_key)


def safe_storage_decrypt(prefixed_encrypted: bytes):
    if not prefixed_encrypted.startswith(b'v10'):
        raise RuntimeError(f'Unknown key version: {prefixed_encrypted[:3]}')
    raw_cyphertext = prefixed_encrypted[3:]

    # Prepare safe storage cipher
    keychain_pw = keyring.get_password('Signal Safe Storage', 'Signal Key').encode()

    # FYI: https://github.com/electron/electron/blob/4e40b49d1a1d55c97ae7853247162347b476e980/shell/browser/api/electron_api_safe_storage.cc#L118
    # Parameters taken from:
    # https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/os_crypt/sync/os_crypt_mac.mm#34
    kek = hashlib.pbkdf2_hmac('sha1', keychain_pw, b'saltysalt', 1003, 128 // 8)

    cipher = AES.new(kek, AES.MODE_CBC, iv=b' ' * 16)
    plaintext = cipher.decrypt(raw_cyphertext)
    return unpad(plaintext, 16).decode('ascii')

key = safe_storage_decrypt(encrypted)

if config.get('x-advanced.reuse_pre_decrypt'):
    db_decrypted = Path('db-decrypt.sqlite')
    db = sqlite3.connect(str(db_decrypted))
    c = db.cursor()

elif config.get('x-advanced.pre_decrypt'):
    db_decrypted = Path('db-decrypt.sqlite')
    sqlcipher = config.get('x-advanced.sqlcipher_bin')
    print(f"Decrypting Signal DB...")
    if db_decrypted.exists():
        db_decrypted.unlink()
    command = (
        f'echo "'
        f"PRAGMA key = \\\"x'{key}'\\\";"
        f"ATTACH DATABASE '{db_decrypted}' AS plaintext KEY '';"
        f"SELECT sqlcipher_export('plaintext');"
        f"DETACH DATABASE plaintext;"
        f'" | {sqlcipher} {db_path}'
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

previous_export_timestamp = dt.datetime.fromisoformat(config.get('last_run'))

# Sqlite query

# List all conversation names
rows = c.execute('select ifnull(name, profileFullName) from conversations order by active_at desc limit 50').fetchall()
config.conversation_list([row[0] for row in rows])

since = previous_export_timestamp.strftime('%Y-%m-%d')
print(f'Querying Signal DB for new images since {since}... ')

query = "SELECT m.json, ifnull(u.name, u.profileName) as user, c.name as conversation, m.body as label, m.sent_at " \
        + "FROM messages m " \
        + "JOIN conversations u ON m.sourceServiceId = u.serviceId " \
        + "JOIN conversations c ON m.conversationId = c.id " \
        + "LEFT JOIN reactions r ON m.id = r.messageId " \
        + "WHERE m.hasVisualMediaAttachments = 1 AND m.type = 'incoming' " \
        + f"AND m.received_at > {int(previous_export_timestamp.timestamp() * 1000)}"

# Filter by reactions
reactions = config.get('import_photos_from_messages.any_with_my_reaction')
if reactions:
    # Get the users conversation ID
    user_id = \
    json.loads(c.execute("select json from items where id = 'uuid_id'").fetchone()[0])['value'].rpartition('.')[0]
    user_convo_id = c.execute(f"select id from conversations where serviceId = '{user_id}'").fetchone()[0]

    # add filter to messages-query
    if '*' in reactions:
        query += f" AND r.fromId = '{user_convo_id}'"
    else:
        reaction_list = "','".join(reactions)
        query += f" AND r.fromId = '{user_convo_id}' AND r.emoji IN ('{reaction_list}')"

# Filter by conversations
convo_include = config.get('import_photos_from_messages.in_conversation.include')
convo_exclude = config.get('import_photos_from_messages.in_conversation.exclude')

if '*' in convo_include and convo_exclude:
    exclude_list = "','".join(convo_exclude)
    query += f" AND c.name NOT IN ('{exclude_list}')"

elif '*' in convo_exclude and convo_include:
    include_list = "','".join(convo_include)
    query += f" AND c.name IN ('{include_list}')"

c.execute(query)
rows = c.fetchall()
print('done.')
print('Export and annotate images.')
most_recent_message = previous_export_timestamp

count_copied = 0
count_present = 0
for payload, user, conversation, label, timestamp in progressbar.progressbar(rows):
    date = dt.datetime.fromtimestamp(timestamp // 1000)
    most_recent_message = max(most_recent_message, date)
    attachments = json.loads(payload)['attachments']
    for index, attachment in enumerate(attachments):
        if not 'path' in attachment:
            continue
        if attachment['contentType'] != 'image/jpeg':
            continue

        filename = slugify(user) + '_' + date.replace(microsecond=0).isoformat().replace(':', '.')
        if len(attachments) > 1:
            filename += f'_{index + 1}'

        target = tmp_folder / (filename + '.jpg')

        if platform == 'linux' and (win_icloud_photos_path / target.name).exists():
            count_present += 1
            continue

        source_path = attachments_path / attachment['path'].replace('\\', '/')
        decrypt_attachment(attachment['size'], attachment['localKey'], source_path, target)
        count_copied += 1

        description = user
        if conversation != user:
            description += f' in "{conversation}"'
        if label:
            description += f': {label}'

        tags = user, 'Signal'
        if conversation != user:
            tags += tagify(conversation),

        description = description.replace('\n', ' ')

        with ExifToolHelper() as et:
            exif = {
                "Model": 'Signal Export',
                "DateTimeOriginal": date.strftime('%Y:%m:%d %H:%M:%S'),
                "Keywords": list(tags),
                "Artist": user,
                "Caption-Abstract": description,
                "ImageDescription": description,
                "CodedCharacterSet": '\x1b%G',
            }
            try:
                et.set_tags([target], tags=exif, params=["-P", "-overwrite_original"])
            except ExifToolExecuteError as e:
                print("Error while writing metadata: ", e)


print('Export complete.')

if count_copied > 0:
    if platform == 'darwin':
        print()
        print('Please drag the tmp-folder on Photos\'s app icon to trigger the import.')

    elif platform == 'linux':
        for img in tmp_folder.iterdir():
            move(str(img), str(win_icloud_photos_path))

config.config['last_run'] = most_recent_message.isoformat()
config.save()

print(f'New images since {since}: {count_copied}')
print(f'Images already in output folder: {count_present}')
print('Press enter to close.')
input()
