#!/usr/bin/python
# encoding: utf-8
#
# Copyright © 2014 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2014-03-09
#

from __future__ import print_function, unicode_literals

"""ff.py -- Fuzzy folder search for Alfred.

Usage:

    <DIR> is a path to a directory.
    <query> may be a query or a dirpath and query joined with DELIMITER
    <PROFILE> is a number referring to a key in `wf.settings['profiles']`

    ff.py choose <DIR>
        Browse <DIR> in Alfred. Displays <DIR> and its subdirectories. Calls
        `ff.py add`
    ff.py add <DIR>
        Add <DIR> as Fuzzy Folder. Tells Alfred to ask for a keyword (via
        `ff.py keyword``).
    ff.py remove <PROFILE>
        Remove <PROFILE> keyword / Fuzzy Folder combination
    ff.py search [<PROFILE>] <query>
        Search for <query> in <PROFILE>'s dirpath. Display results in Alfred.
    ff.py searchdir <query>
        Ad-hoc folder searches. <query> is a dirpath and query. Display
        results in Alfred.
    ff.py keyword <query>
        Choose a keyword for Fuzzy Folder. <query> is a dirpath and query.
        Display options in Alfred. Calls `ff.py update <query>`.
    ff.py update [<query>]
        Update/add the Fuzzy Folder / keyword profile in <query>. If no
        <query> is specified, updates all profiles.
    ff.py manage [<query>]
        Display a list of all configured profiles in Alfred. Allows activation
        or deletion of the profiles.
    ff.py load-profile <PROFILE>
        Calls Alfred with the necessary keyword to activate <PROFILE>
    ff.py alfred-search <query>
        Calls Alfred with <query>. Simple, pass-through function.
    ff.py alfred-browse <DIR>
        Calls Alfred with <DIR>, causing Alfred's browser to activate.

"""

import sys
import os
import subprocess
import re
from plistlib import readPlist, writePlist
import uuid
import unicodedata

from workflow import Workflow, ICON_NOTE, ICON_WARNING, ICON_INFO
from workflow.workflow import MATCH_ALL, MATCH_ALLCHARS


__version__ = '1.0'
__usage__ = """
ff.py <action> [<DIR> | <PROFILE>] [<query>]

FuzzyFolders -- fuzzy search across a folder hierarchy

Usage:
    ff.py choose <DIR>
    ff.py add <DIR>
    ff.py remove <PROFILE>
    ff.py search [<PROFILE>] <query>
    ff.py searchdir <query>
    ff.py keyword <query>
    ff.py update [<query>]
    ff.py manage [<query>]
    ff.py load-profile <PROFILE>
    ff.py alfred-search <query>
    ff.py alfred-browse <DIR>

This script is meant to be called from Alfred.

"""

log = None
DELIMITER = '➣'

ALFRED_SCRIPT = """tell application "Alfred 2"
    search "{}"
end tell
"""

# Keywords of script filters that shouldn't be removed
RESERVED_KEYWORDS = [
    ':fuzzychoose',
    ':fuzzykeyword',
    ':fuzzysearch',
    ':fuzzyupdate'
    'fuzzy'
]

YPOS_START = 690
YSIZE = 120


SCRIPT_SEARCH = re.compile(r"""python ff.py search (\d+)""").search


def _applescriptify(text):
    """Replace double quotes in text"""
    return text.replace('"', '" + quote + "')


def run_alfred(query):
    """Run Alfred with ``query`` via AppleScript"""
    script = ALFRED_SCRIPT.format(_applescriptify(query))
    log.debug('calling Alfred with : {!r}'.format(script))
    return subprocess.call(['osascript', '-e', script])


def search_in(root, query, dirs_only=True):
    """Search for files under `root` matching `query`

    If `dirs_only` is True, only search for directories.

    """

    cmd = ['mdfind', '-onlyin', root]
    query = ["(kMDItemFSName == '*{}*'c)".format(query)]
    if dirs_only:
        query.append("(kMDItemContentType == 'public.folder')")
    cmd.append(' && '.join(query))
    log.debug(cmd)
    output = subprocess.check_output(cmd).decode('utf-8')
    output = unicodedata.normalize('NFC', output)
    paths = [s.strip() for s in output.split('\n') if s.strip()]
    log.debug('{:d} hits from Spotlight index'.format(len(paths)))
    return paths


def filter_paths(queries, paths, root):
    """Return subset of `paths` whose path segments contain the elements
    in ``queries` in the same order. Case-insensitive.

    """

    hits = set()
    queries = [q.lower() for q in queries]
    for i, p in enumerate(paths):
        # Split path into lower-case components,
        # removing the last one (matched by Spotlight)
        components = p.replace(root, '').lower().split('/')[:-1]
        matches = 0
        for q in queries:
            for j, s in enumerate(components):
                if q in s:
                    log.debug('{!r} in {!r}'.format(q, components))
                    matches += 1
                    components = components[j:]
                    break
        if matches == len(queries):
            log.debug('match: {!r} --> {!r}'.format(queries, p))
            hits.add(i)
    log.debug('{:d}/{:d} after filtering'.format(len(hits), len(paths)))
    return [p for i, p in enumerate(paths) if i in hits]


class Dirpath(unicode):

    @classmethod
    def dirpath(cls, path):
        return Dirpath(os.path.abspath(os.path.expanduser(path)))

    @property
    def abs_slash(self):
        """Return absolute path with trailing slash"""
        p = os.path.abspath(self)
        if not p.endswith('/'):
            return p + '/'
        return p

    @property
    def abs_noslash(self):
        """Return absolute path with no trailing slash"""
        p = os.path.abspath(self)
        if p.endswith('/') and p not in ('/', '~/'):
            return p[:-1]
        return p

    @property
    def abbr_slash(self):
        """Return abbreviated path with trailing slash"""
        p = self.abs_slash.replace(os.path.expanduser('~/'), '~/')
        if not p.endswith('/'):
            return p + '/'
        return p

    @property
    def abbr_noslash(self):
        """Return abbreviated path with no trailing slash"""
        p = self.abs_slash.replace(os.path.expanduser('~/'), '~/')
        if p.endswith('/') and p not in ('/', '~/'):
            return p[:-1]
        return p

    def splitquery(self):
        """Split into dirpath and query"""
        if not os.path.exists(self.abs_slash):
            pos = self.abs_noslash.rfind('/')
            if pos > -1:  # query
                if pos == 0:
                    dirpath = Dirpath.dirpath('/')
                else:
                    dirpath = Dirpath.dirpath(self[:pos])
                query = self[pos+1:]
                log.debug('dirpath : {!r}  query : {!r}'.format(dirpath, query))
                return dirpath, query
        return self, ''


class FuzzyFolders(object):

    def __init__(self, wf):
        self.wf = wf
        self.dirpath = None
        self.query = None

    def run(self, args):
        if args['<DIR>']:
            self.dirpath = Dirpath.dirpath(args['<DIR>'])
        self.query = args['<query>']
        self.profile = args['<PROFILE>']
        log.debug('dirpath : {!r}  query : {!r}'.format(self.dirpath,
                                                        self.query))

        if args.get('choose'):
            return self.do_choose()
        if args.get('add'):
            return self.do_add()
        elif args.get('remove'):
            return self.do_remove()
        elif args.get('search'):
            return self.do_search()
        elif args.get('searchdir'):
            return self.do_ad_hoc_search()
        elif args.get('keyword'):
            return self.do_choose_keyword()
        elif args.get('update'):
            return self.do_update()
        elif args.get('manage'):
            return self.do_manage()
        elif args.get('load-profile'):
            return self.do_load_profile()
        elif args.get('alfred-search'):
            return self.do_alfred_search()
        elif args.get('alfred-browse'):
            return self.do_alfred_browse()
        else:
            raise ValueError('No action specified')

    def do_choose(self):
        """Show a list of subdirectories of ``self.dirpath`` to choose from"""
        dirpath, query = self.dirpath.splitquery()
        log.debug('dirpath : {!r}  query : {!r}'.format(dirpath, query))
        if not os.path.exists(dirpath) or not os.path.isdir(dirpath):
            log.debug('Does not exist/not a directory : {!r}'.format(dirpath))
            return 0
        if not query:
            self.wf.add_item(
                dirpath.abbr_noslash,
                'Add {} as a new Fuzzy Folder'.format(dirpath.abbr_noslash),
                arg=dirpath.abs_slash,
                autocomplete=dirpath.abbr_slash,
                valid=True,
                icon=dirpath.abs_noslash,
                icontype='fileicon',
                type='file')
        files = []
        for filename in os.listdir(dirpath):
            p = os.path.join(dirpath, filename)
            if os.path.isdir(p) and not filename.startswith('.'):
                files.append((filename, p))
        log.debug('{:d} folders in {!r}'.format(len(files), dirpath))
        if files and query:
            log.debug('filtering {:d} files against {!r}'.format(len(files),
                                                                 query))
            files = self.wf.filter(query, files, key=lambda x: x[0])
        for filename, p in files:
            p = Dirpath.dirpath(p)
            self.wf.add_item(
                filename,
                'Add {} as a new Fuzzy Folder'.format(p.abbr_noslash),
                arg=p.abs_noslash,
                autocomplete=p.abbr_slash,
                valid=True,
                icon=p.abs_noslash,
                icontype='fileicon',
                type='file')
        self.wf.send_feedback()

    def do_add(self):
        """Tell Alfred to ask for ``keyword``"""
        return run_alfred(':fuzzykeyword {} {} '.format(
            self.dirpath.abbr_noslash, DELIMITER))

    def do_remove(self):
        """Remove existing folder"""
        profiles = self.wf.settings.get('profiles', {})
        if self.profile in profiles:
            log.debug('Removing profile {} ...'.format(self.profile))
            del profiles[self.profile]
            self.wf.settings['profiles'] = profiles
            self._update_script_filters()
            print('Deleted keyword / Fuzzy Folder')
        else:
            log.debug('No such profile {} ...'.format(self.profile))
            print('No such keyword / Fuzzy Folder')

    def do_search(self):
        """Search Fuzzy Folder."""
        profile = self.wf.settings.get('profiles', {}).get(self.profile)
        if not profile:
            log.debug('Profile not found : {}'.format(self.profile))
            return 1

        root = profile['dirpath']
        query = self.query.split()

        if len(query) > 1:
            mdquery = query[-1]
            query = query[:-1]
        else:
            mdquery = query[0]
            query = None

        log.debug('mdquery : {!r}  query : {!r}'.format(mdquery, query))
        paths = search_in(root, mdquery)

        if query:
            paths = filter_paths(query, paths, root)

        home = os.path.expanduser('~/')
        for path in paths:
            filename = os.path.basename(path)
            wf.add_item(filename, path.replace(home, '~/'),
                        valid=True, arg=path,
                        autocomplete=filename,
                        uid=path, type='file',
                        icon=path, icontype='fileicon')

        wf.send_feedback()
        log.debug('finished search')
        return 0

    def do_ad_hoc_search(self):
        """Search in directory not stored in a profile"""
        if DELIMITER not in self.query:  # bounce path back to Alfred
            log.debug('No delimiter found')
            run_alfred(self.query)
            # run_alfred(':fuzzychoose {}'.format(Dirpath.dirpath(
            #            self.query.strip()).abbr_slash))
            return 0
        root, query = self._parse_query(self.query)
        log.debug('root : {!r}  query : {!r}'.format(root, query))
        if not query:
            return 0

        query = query.split()

        if len(query) > 1:
            mdquery = query[-1]
            query = query[:-1]
        else:
            mdquery = query[0]
            query = None

        log.debug('mdquery : {!r}  query : {!r}'.format(mdquery, query))
        paths = search_in(root, mdquery)

        if query:
            paths = filter_paths(query, paths, root)

        home = os.path.expanduser('~/')
        for path in paths:
            filename = os.path.basename(path)
            wf.add_item(filename, path.replace(home, '~/'),
                        valid=True, arg=path,
                        uid=path, type='file',
                        icon=path, icontype='fileicon')

        wf.send_feedback()
        log.debug('finished search')

    def do_load_profile(self):
        """Load the corresponding profile in Alfred"""
        profile = self.wf.settings.get('profiles', {}).get(self.profile)
        log.debug('loading profile {!r}'.format(profile))
        return run_alfred('{} '.format(profile['keyword']))

    def do_manage(self):
        """Show list of existing profiles"""
        profiles = self.wf.settings.get('profiles', {})

        if self.query:
            items = profiles.items()
            items = self.wf.filter(self.query, items,
                                   key=lambda t: '{} {}'.format(
                                   t[1]['keyword'], t[1]['dirpath']),
                                   match_on=MATCH_ALL ^ MATCH_ALLCHARS)
            profiles = dict(items)

        for num, profile in profiles.items():
            self.wf.add_item('{} {} {}'.format(profile['keyword'], DELIMITER,
                             Dirpath.dirpath(profile['dirpath']).abbr_noslash),
                             'Hit ENTER to search keyword',
                             valid=True,
                             arg=num,
                             autocomplete=profile['keyword'],
                             icon='icon.png')

        self.wf.send_feedback()

    def do_choose_keyword(self):
        """Choose keyword for folder in Alfred."""

        dirpath, keyword = self._parse_query(self.query)
        log.debug('dirpath : {!r}  keyword : {!r}'.format(dirpath, keyword))

        # check for existing configurations for this dirpath and keyword
        profiles = []
        profile_exists = False
        keyword_warnings = []
        dirpath_warnings = []
        for profile in self.wf.settings.get('profiles', {}).values():
            profiles.append((profile['keyword'], profile['dirpath']))

        if (keyword, dirpath.abs_noslash) in profiles:
            profile_exists = True

        for k, p in profiles:
            if keyword == k:
                keyword_warnings.append("'{}' searches {}".format(
                                        k, Dirpath.dirpath(p).abbr_noslash))
            elif dirpath.abs_noslash == p:
                dirpath_warnings.append(
                    "Folder already linked to '{}'".format(k))

        if self.query.endswith(DELIMITER):  # user has deleted trailing space
            # back up the file tree
            return run_alfred(':fuzzychoose {}'.format(
                Dirpath.dirpath(os.path.dirname(dirpath)).abbr_slash))
            return self.do_add()
        elif keyword == '':  # no keyword as yet
            if not keyword:
                self.wf.add_item('Enter a keyword for the Folder',
                                 dirpath,
                                 valid=False,
                                 icon=ICON_NOTE)
                for warning in dirpath_warnings:
                    self.wf.add_item(warning,
                        'But you can set multiple keywords per folders',
                        valid=False,
                        icon=ICON_INFO)
                self.wf.send_feedback()
                return 0
        else:  # offer to set keyword
            if profile_exists:
                self.wf.add_item(
                    'This keyword > Fuzzy Folder already exists',
                    "'{}' already linked to {}".format(
                    keyword,
                    dirpath.abbr_noslash),
                    valid=False,
                    icon=ICON_WARNING)
            else:
                self.wf.add_item("Set '{}' as keyword for {}".format(
                    keyword, dirpath.abbr_noslash),
                    dirpath,
                    arg='{} {} {}'.format(dirpath, DELIMITER, keyword),
                    valid=True,
                    icon='icon.png')
                for warning in dirpath_warnings:
                    self.wf.add_item(warning,
                        'But you can set multiple keywords per folders',
                        valid=False,
                        icon=ICON_INFO)
                for warning in keyword_warnings:
                    self.wf.add_item(warning,
                        'But you can use the same keyword for multiple folders',
                        valid=False,
                        icon=ICON_INFO)
            self.wf.send_feedback()

    def do_update(self):
        """Save new/updated Script Filter to info.plist."""

        if not self.query:  # Just do an update
            self._update_script_filters()
            return 0

        dirpath, keyword = self._parse_query(self.query)
        log.debug('dirpath : {!r}  keyword : {!r}'.format(dirpath, keyword))
        profiles = self.wf.settings.setdefault('profiles', {})
        log.debug('profiles : {!r}'.format(profiles))
        if not profiles:
            last = 0
        else:
            last = max([int(s) for s in profiles.keys()])
        log.debug('Last profile : {:d}'.format(last))
        profile = dict(keyword=keyword, dirpath=dirpath)
        profiles[unicode(last + 1)] = profile  # JSON requires string keys
        self.wf.settings['profiles'] = profiles
        self._update_script_filters()
        print("Keyword '{}' searches {}".format(
              keyword, Dirpath.dirpath(dirpath).abbr_noslash))

    def do_alfred_search(self):
        """Initiate an ad-hoc search in Alfred"""
        return run_alfred(':fuzzysearch {} {} '.format(self.query, DELIMITER))

    def do_alfred_browse(self):
        """Open directory in Alfred"""
        return run_alfred(self.dirpath)

    def _update_script_filters(self):
        """Create / update Script Filters in info.plist to match settings."""
        plistpath = self.wf.workflowfile('info.plist')
        plisttemp = self.wf.workflowfile('info.plist.temp')

        profiles = self.wf.settings.get('profiles', {})

        self._reset_script_filters()

        plist = readPlist(plistpath)
        objects = plist['objects']
        uidata = plist['uidata']
        connections = plist['connections']

        y_pos = YPOS_START
        for num, profile in profiles.items():
            uid = unicode(uuid.uuid4()).upper()
            dirname = Dirpath.dirpath(profile['dirpath']).abbr_noslash
            script_filter = {
                'type': 'alfred.workflow.input.scriptfilter',
                'uid': uid,
                'version': 0
            }
            config = {
                'argumenttype': 0,
                'escaping': 102,
                'keyword': profile['keyword'],
                'runningsubtext': 'Loading files\u2026',
                'script': 'python ff.py search {} "{{query}}"'.format(num),
                'subtext': 'Fuzzy search across subdirectories of {}'.format(
                    dirname),
                'title': 'Fuzzy Search {}'.format(dirname),
                'type': 0,
                'withspace': True
            }
            script_filter['config'] = config
            objects.append(script_filter)
            # set position
            uidata[uid] = {'ypos': float(y_pos)}
            y_pos += YSIZE
            # add connection to Browse in Alfred action
            connections[uid] = [
                {'destinationuid': '3AC082E0-F48F-4094-8B54-E039CDBC418B',
                 'modifiers': 1048576,
                 'modifiersubtext': 'Browse in Alfred'}
            ]

        plist['objects'] = objects
        plist['uidata'] = uidata
        plist['connections'] = connections

        writePlist(plist, plisttemp)
        os.unlink(plistpath)
        os.rename(plisttemp, plistpath)
        os.utime(plistpath, None)

        log.debug('Wrote {:d} script filters to info.plist'.format(
                  len(profiles)))

    def _dirpath_abbr(self, dirpath=None):
        """Return attr:`~FuzzyFolders.dirpath` with ``$HOME`` replaced
        with ``~/``

        """

        if not dirpath:
            dirpath = self.dirpath
        if not dirpath.endswith('/'):
            dirpath += '/'
        dirpath = dirpath.replace(os.path.expanduser('~/'), '~/')
        if dirpath.endswith('/') and dirpath not in ('/', '~/'):
            dirpath = dirpath[:-1]
        return dirpath

    def _parse_query(self, query):
        """Split ``query`` into ``dirpath`` and ``query``.

        :returns: ``(dirpath, query)`` where either may be empty
        """

        components = query.split(DELIMITER)
        if not len(components) == 2:
            raise ValueError('Too many components in : {!r}'.format(query))
        dirpath, query = [s.strip() for s in components]
        dirpath = Dirpath.dirpath(dirpath)
        return (dirpath, query)

    def _reset_script_filters(self):
        """Load script filters from `info.plist`"""

        plistpath = self.wf.workflowfile('info.plist')

        # backup info.plist
        with open(plistpath, 'rb') as infile:
            with open(self.wf.workflowfile('info.plist.bak'), 'wb') as outfile:
                outfile.write(infile.read())

        script_filters = {}
        plist = readPlist(plistpath)

        count = 0
        keep = []
        uids = set()
        for obj in plist['objects']:
            if obj.get('type') != 'alfred.workflow.input.scriptfilter':
                keep.append(obj)
                continue
            if obj.get('keyword') in RESERVED_KEYWORDS:
                keep.append(obj)
                continue

            script = obj.get('config', {}).get('script', '')
            log.debug('script : {!r}'.format(script))
            m = SCRIPT_SEARCH(script)
            if not m:
                keep.append(obj)
                continue

            count += 1
            uids.add(obj['uid'])

        # Overwrite objects minus script filters
        plist['objects'] = keep

        # Delete positioning data
        keep = {}
        uidata = plist['uidata']
        for uid in uidata:
            if uid not in uids:
                keep[uid] = uidata[uid]

        # Overwrite without script filter positions
        plist['uidata'] = keep

        # Remove connections
        keep = {}
        connections = plist['connections']
        for uid in connections:
            if uid not in uids:
                keep[uid] = connections[uid]

        # Overwrite without script filter connections
        plist['connections'] = keep

        # Re-write info.plist without script filters

        writePlist(plist, plistpath)

        log.debug('{} script filters deleted from info.plist'.format(count))
        return script_filters


def main(wf):
    from docopt import docopt
    args = docopt(__usage__, argv=wf.args, version=__version__)
    log.debug('wf.args : {!r}'.format(wf.args))
    log.debug('args : {!r}'.format(args))
    ff = FuzzyFolders(wf)
    return ff.run(args)


if __name__ == '__main__':
    wf = Workflow(libraries=[os.path.join(os.path.dirname(__file__), 'lib')])
    log = wf.logger
    sys.exit(wf.run(main))
