
import base64
import hashlib
import hmac
from pathlib import Path

import keyring
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

CIPHER_KEY_SIZE = 32
IV_SIZE = AES.block_size
MAC_KEY_SIZE = 32
MAC_SIZE = hashlib.sha256().digest_size

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

# Adapted from: https://github.com/carderne/signal-export/blob/main/sigexport/files.py
def decrypt_attachment(size: int, key: str, src_path: Path, dst_path: Path) -> None:
    """Decrypt attachment and save to `dst_path`.

    Code adapted from:
        https://github.com/tbvdm/sigtop
    """
    try:
        keys = base64.b64decode(key)
    except KeyError:
        raise ValueError("No key in attachment")
    except Exception as e:
        raise ValueError(f"Cannot decode keys: {str(e)}")

    if len(keys) != CIPHER_KEY_SIZE + MAC_KEY_SIZE:
        raise ValueError("Invalid keys length")

    cipher_key = keys[:CIPHER_KEY_SIZE]
    mac_key = keys[CIPHER_KEY_SIZE:]

    try:
        with open(src_path, "rb") as fp:
            data = fp.read()
    except Exception as e:
        raise ValueError(f"Failed to read file: {str(e)}")

    if len(data) < IV_SIZE + MAC_SIZE:
        raise ValueError("Attachment data too short")

    iv = data[:IV_SIZE]
    their_mac = data[-MAC_SIZE:]
    data = data[IV_SIZE:-MAC_SIZE]

    if len(data) % AES.block_size != 0:
        raise ValueError("Invalid attachment data length")

    m = hmac.new(mac_key, iv + data, hashlib.sha256)
    our_mac = m.digest()

    if not hmac.compare_digest(our_mac, their_mac):
        raise ValueError("MAC mismatch")

    try:
        cipher = AES.new(cipher_key, AES.MODE_CBC, iv)
        decrypted_data = cipher.decrypt(data)
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")

    if len(decrypted_data) < size:
        raise ValueError("Invalid attachment data length")

    data_decrypted = decrypted_data[: size]
    with open(dst_path, "wb") as fp:
        fp.write(data_decrypted)
