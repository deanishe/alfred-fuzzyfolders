#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2014 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2014-04-02
#

"""
"""

from __future__ import print_function, unicode_literals

import os
import subprocess
from time import time


DIRS = [os.path.expanduser('~/Documents'), '/Volumes/Media/Video']


def get_num_results(cmd):
    s = time()
    output = subprocess.check_output(cmd).decode('utf-8')
    print('\t`mdfind` finished in {:0.4f} seconds'.format(time() - s))
    lines = [l.strip() for l in output.split('\n') if l.strip()]
    return len(lines)

for root in DIRS:
    for query in ('i', 'in', 'inl'):
        basecmd = ['mdfind', '-onlyin', root]
        file_cmd = basecmd + ["(kMDItemFSName == '*{}*'c)".format(query)]
        dir_cmd = basecmd + ["(kMDItemFSName == '*{}*'c) && (kMDItemContentType == 'public.folder')".format(query)]
        s = time()
        print('{} files found for `{}` in `{}` in {:0.4f} seconds'.format(
              get_num_results(file_cmd), query, root, time() - s))
        s = time()
        print('{} folders found for `{}` in `{}` in {:0.4f} seconds'.format(
              get_num_results(dir_cmd), query, root, time() - s))
