#!/usr/bin/env python3
assert __name__ == '__main__'

import cc_shimmer

import base64
import hashlib
import logging
import os
import shutil
import subprocess
import sys

####

CONFIG_PATH = os.path.expanduser('~/.ocache.py')

####

def load_config(path=CONFIG_PATH):
    with open(path, 'rb') as f:
        code = f.read()
        #code = compile(code, path, 'exec')

        config_scope = {}
        exec(code, config_scope)
    del config_scope['__builtins__']
    return config_scope

####

def path_for_digest(digest_bytes):
    enc = base64.urlsafe_b64encode(digest_bytes)
    enc = enc.decode()
    return os.path.join(enc[0:2], enc)

####

def copytree_to(src_dir, dest_dir):
    for (src_cur_dir, dirs, files) in os.walk(src_dir):
        relpath = os.path.relpath(src_cur_dir, src_dir)
        dest_cur_dir = os.path.join(dest_dir, relpath)

        for x in files:
            shutil.copy2(os.path.join(src_cur_dir, x), dest_cur_dir)

        for x in dirs:
            os.mkdir(os.path.join(dest_cur_dir, x))

####

# sys.argv: [ocache.py, cl, foo.c]

args = sys.argv[1:]
assert args

logger = logging.getLogger()

logger.setLevel(40)

while args[0].startswith('-'):
    arg = args.pop(0)
    if arg == '-v':
        logger.setLevel(30)
        continue
    if arg == '-vv':
        logger.setLevel(20)
        continue
    if arg == '-vvv':
        logger.setLevel(10)
        continue

    if arg == '--clear':
        config = load_config()
        CACHE_DIR = config['CACHE_DIR']
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        print("Cache cleared.")
        exit(0)

    print('Unknown flag: {}'.format(arg))
    exit(1)

try:
    (preproc_args, compile_args, source_file_name) = cc_shimmer.process_args(args)

    info = 'ccerb-preproc: {}'.format(source_file_name)

    logging.debug('<<preproc_args: {}>>'.format(preproc_args))
    logging.debug('<<compile_args: {}>>'.format(compile_args))

    # Get this started:
    p = subprocess.Popen(preproc_args, bufsize=-1, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True)

    ####

    # Read the config while that's going
    config = load_config()

    ####

    (outdata, errdata) = p.communicate()
    if p.returncode != 0:
        sys.stderr.write(errdata)
        sys.stdout.write(outdata)
        exit(p.returncode)

    preproc_data = outdata

    ####

    hasher = hashlib.blake2b()
    hasher.update(str(args).encode())
    hasher.update(preproc_data.encode())
    digest = hasher.digest()

    ####

    CACHE_DIR = config['CACHE_DIR']

    cached_base_dir = os.path.join(CACHE_DIR, path_for_digest(digest))
    cached_files_dir = os.path.join(cached_base_dir, 'files')
    cached_stdout_path = os.path.join(cached_base_dir, 'stdout')
    cached_stderr_path = os.path.join(cached_base_dir, 'stderr')

    if not os.path.exists(cached_base_dir):
        input_files = {}
        input_files[source_file_name] = preproc_data
        with cc_shimmer.ScopedTempDir() as temp_dir:
            (returncode, outdata,
             errdata) = cc_shimmer.run_in_dir(temp_dir.path, input_files, compile_args)

            if returncode == 0:
                shutil.copytree(temp_dir.path, cached_files_dir)
        if returncode != 0:
            sys.stderr.write(errdata)
            sys.stdout.write(outdata)
            exit(returncode)

        with open(cached_stdout_path, 'wb') as f:
            f.write(outdata.encode())
        with open(cached_stderr_path, 'wb') as f:
            f.write(errdata.encode())
    else:
        logging.info('[{}] Pulling from cache'.format(source_file_name))
        with open(cached_stdout_path, 'rb') as f:
            outdata = f.read().decode()
        with open(cached_stderr_path, 'rb') as f:
            errdata = f.read().decode()

    copytree_to(cached_files_dir, os.curdir)
    sys.stderr.write(errdata)
    sys.stdout.write(outdata)
    exit(0)

except cc_shimmer.ExShimOut as e:
    logging.warning('<shimming out: \'{}\'>'.format(e.reason))
    logging.info('<<shimming out args: {}>>'.format(args))
    pass

####

p = subprocess.Popen(args)
p.communicate()

exit(p.returncode)
