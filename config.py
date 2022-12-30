import pyfiglet
import yaml
from pathlib import Path
from os import linesep
from sys import platform


config_yaml = Path('config.yaml')

def defaults():
    pre_decrypt = False
    if platform == 'darwin':
        signal_path = Path('~/Library/Application Support/Signal').expanduser()
        photos_path = Path('./images')
        if not photos_path.exists():
            photos_path.mkdir()

    elif platform == 'linux': # ie. WSL
        pre_decrypt = True
        parts = Path.cwd().parts
        userdir_parts = parts[0:parts.index('Users') + 2]
        userdir = Path(*userdir_parts)
        signal_path = userdir / 'AppData/Roaming/Signal'
        photos_path = userdir / 'Pictures/iCloud Photos/Photos'

    else:
        raise NotImplementedError('Platform is not supported:', platform)

    return {
        'import_photos_from_messages': {
            'any_with_my_reaction': [],
            'in_conversation': {
                'include': ['*'],
                'exclude': []
            }
        },
        'output_path': str(photos_path),
        'x-advanced': {
            'signal_path': str(signal_path),
            'pre_decrypt': pre_decrypt,
            'pre_copy': pre_decrypt,
            'sqlcipher_bin': './sqlcipher/bin/sqlcipher'
        } ,
        'last_run': 0
    }  

def load():
    global config
    if not config_yaml.exists():
        config = defaults()
        save()
        print('This is a first run. Please check the generated "config.yaml", modify and press enter to continue (config will be reloaded).')
        input()
        load()
    else:
        with open(config_yaml) as f:
            config = yaml.safe_load(f)

    convo_filter = get('import_photos_from_messages.in_conversation')
    if ('*' in convo_filter['include']) == ('*' in convo_filter['exclude']):
        raise RuntimeError('Invalid conversation filters. Either one of "include" or "exclude" needs to contain the glob "*".')

def save():
    with open(config_yaml, 'w') as f:
        header = (linesep + pyfiglet.figlet_format('Configuration', font='smscript')).replace(linesep, linesep + '#   ', 5)
        f.write(header + linesep)
        yaml.safe_dump(config, f, allow_unicode=True)

def get(path):
    handle = config
    for key in path.split('.'):
        handle = handle.get(key)

    return handle

def add_conversations(conversations):
    include = set(config['import_messages']['by_conversation']['include']).union(conversations)
    config['import_messages']['by_conversation']['include'] = list(include)
