"""
ipython startup script
10-keychain.py

Defines a function for getting secret values out of the keychain
"""

import getpass
import subprocess


def get_keychain_password(service: str) -> str:
     return subprocess.run([
         'security', 'find-generic-password',
         '-w', '-a', getpass.getuser(),
         '-s', service,
     ], stdout=subprocess.PIPE).stdout.decode('utf-8').strip('\n')
