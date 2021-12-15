#!/usr/bin/python
# encoding: utf-8
#
# Copyright (c) 2014 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2014-03-09
#

"""ff.py <action> [<dir> | <profile>] [<query>]

FuzzyFolders -- fuzzy search across a folder hierarchy

Usage:
    ff.py choose <dir>
    ff.py add <dir>
    ff.py remove <profile>
    ff.py search <query> [<profile>]
    ff.py keyword <query>
    ff.py update [<query>]
    ff.py manage [<query>]
    ff.py load-profile <profile>
    ff.py alfred-search <query>
    ff.py alfred-browse <dir>
    ff.py load-settings <profile>
    ff.py settings <query>
    ff.py update-setting <query>
    ff.py open-help

Arguments:
    <dir>       Path to directory
    <profile>   Saved profile number
    <query>     Search query

Options:
    -h, --help  Show this message


Commands:
    choose <dir>
        Browse <dir> in Alfred. Displays <dir> and its subdirectories. Calls  `add`
    add <dir>
        Add <dir> as Fuzzy Folder. Tells Alfred to ask for a keyword (via `keyword``).
    remove <profile>
        Remove <profile> keyword / Fuzzy Folder combination
    search <query> [<profile>]
        Search for <query> in <profile>'s dirpath. Display results in Alfred.
        If no <profile> is specified, <query> is a dirpath-DELIMITER-query
        combination. Start an ad-hoc fuzzy search with this.
    keyword <query>
        Choose a keyword for Fuzzy Folder. <query> is a dirpath and query.
        Display options in Alfred. Calls `update <query>`.
    update [<query>]
        Update/add the Fuzzy Folder / keyword profile in <query>. If no
        <query> is specified, updates all profiles.
    manage [<query>]
        Display a list of all configured profiles in Alfred. Allows activation
        or deletion of the profiles.
    load-profile <profile>
        Calls Alfred with the necessary keyword to activate <profile>
    alfred-search <query>
        Calls Alfred with <query>. Simple, pass-through function.
    alfred-browse <dir>
        Calls Alfred with <dir>, causing Alfred's browser to activate.
    open-help
        Open the help file in your browser

This script is meant to be called from Alfred.

"""

from __future__ import print_function, unicode_literals

import sys
import os
import subprocess
import re
from fnmatch import fnmatch
from plistlib import readPlist, writePlist
import uuid
import unicodedata

from docopt import docopt
from workflow import (Workflow, ICON_NOTE, ICON_WARNING,
                      ICON_INFO, ICON_SETTINGS, ICON_ERROR, ICON_SYNC)
from workflow.util import reload_workflow, run_trigger, search_in_alfred
from workflow.workflow import MATCH_ALL, MATCH_ALLCHARS


log = None
DELIMITER = '➣'

# Keywords of Script Filters that shouldn't be removed
RESERVED_KEYWORDS = [
    'fzyup',
    'fzyhelp',
    'fuzzy'
]


# actions to connect script filters to
ACTIONS = [
    # Browse folder in Alfred
    {'destinationuid': '3AC082E0-F48F-4094-8B54-E039CDBC418B',
     'modifiers': 1048576,
     'modifiersubtext': 'Browse in Alfred'},
    # Run keyword search
    {'destinationuid': '8DA965F1-FBE5-4283-A66A-05789AA78758',
     'modifiers': '',
     'modifiersubtext': ''},
]


SCOPE_FOLDERS = 1
SCOPE_FILES = 2
SCOPE_ALL = 3

SCOPE_NAMES = {
    SCOPE_FOLDERS: 'folders only',
    SCOPE_FILES: 'files only',
    SCOPE_ALL: 'folders and files'
}

DEFAULT_SETTINGS = {
    'min': 1,
    'scope': SCOPE_FOLDERS
}

YPOS_START = 1360
YSIZE = 135


SCRIPT_SEARCH = re.compile(r"""python ff.py search ".+?" (\d+)""").search


def search_in(root, query, scope):
    """Search for files under `root` matching `query`.

    If `dirs_only` is True, only search for directories.

    """
    cmd = ['mdfind', '-onlyin', root]
    query = ["(kMDItemFSName == '*{}*'c)".format(query)]
    if scope == SCOPE_FOLDERS:
        query.append("(kMDItemContentType == 'public.folder')")
    elif scope == SCOPE_FILES:
        query.append("(kMDItemContentType != 'public.folder')")

    cmd.append(' && '.join(query))
    log.debug(cmd)
    output = subprocess.check_output(cmd).decode('utf-8')
    output = unicodedata.normalize('NFC', output)
    paths = [s.strip() for s in output.split('\n') if s.strip()]
    log.debug('%d hits from Spotlight index', len(paths))
    return paths


def filter_excludes(paths, root, patterns):
    """Return subset of `paths` not matching patterns.

    `root` is the root fuzzy folder. It's removed from paths before
    matching.

    """
    log.debug('exclude patterns: %r', patterns)
    hits = []
    for path in paths:
        search_path = path.replace(root, '')
        for pat in patterns:
            match = False
            if fnmatch(search_path, pat):
                log.debug('match: %r --> %r', pat, search_path)
                match = True
                break
        if match:
            continue
        else:
            hits.append(path)
    log.debug('%d/%d after blacklist filtering', len(hits), len(paths))
    return hits


def filter_paths(queries, paths, root):
    """Return subset of `paths` that match `queries`.

    Matching `paths` are those whose path segments contain the elements
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
                    log.debug('%r in %r', q, components)
                    matches += 1
                    components = components[j:]
                    break
        if matches == len(queries):
            log.debug('match: %r --> %r', queries, p)
            hits.add(i)
    log.debug('%d/%d after filtering', len(hits), len(paths))
    return [p for i, p in enumerate(paths) if i in hits]


class Dirpath(unicode):
    """Helper for formatting directory paths."""

    @classmethod
    def dirpath(cls, path):
        """Create a new `Dirpath`."""
        return Dirpath(os.path.abspath(os.path.expanduser(path)))

    @property
    def abs_slash(self):
        """Return absolute path with trailing slash."""
        p = os.path.abspath(self)
        if not p.endswith('/'):
            return p + '/'
        return p

    @property
    def abs_noslash(self):
        """Return absolute path with no trailing slash."""
        p = os.path.abspath(self)
        if p.endswith('/') and p not in ('/', '~/'):
            return p[:-1]
        return p

    @property
    def abbr_slash(self):
        """Return abbreviated path with trailing slash."""
        p = self.abs_slash.replace(os.path.expanduser('~/'), '~/')
        if not p.endswith('/'):
            return p + '/'
        return p

    @property
    def abbr_noslash(self):
        """Return abbreviated path with no trailing slash."""
        p = self.abs_slash.replace(os.path.expanduser('~/'), '~/')
        if p.endswith('/') and p not in ('/', '~/'):
            return p[:-1]
        return p

    def splitquery(self):
        """Split into dirpath and query."""
        if not os.path.exists(self.abs_slash):
            pos = self.abs_noslash.rfind('/')
            if pos > -1:  # query
                if pos == 0:
                    dirpath = Dirpath.dirpath('/')
                else:
                    dirpath = Dirpath.dirpath(self[:pos])

                query = self[pos+1:]
                log.debug('dirpath=%r,  query=%r', dirpath, query)
                return dirpath, query

        return self, ''


class FuzzyFolders(object):
    """Application controller."""

    def __init__(self, wf):
        """Create a new `FuzzyFolder` object."""
        self.wf = wf
        self.dirpath = None
        self.query = None

    def run(self, args):
        """Run the workflow/application."""
        # install default settings if there are none
        if 'defaults' not in self.wf.settings:
            self.wf.settings['defaults'] = DEFAULT_SETTINGS

        if args['<dir>']:
            self.dirpath = Dirpath.dirpath(args['<dir>'])
        self.query = args['<query>']
        self.profile = args['<profile>']
        log.debug('dirpath=%r,  query=%r', self.dirpath, self.query)

        actions = ('choose', 'add', 'remove', 'search', 'keyword',
                   'update', 'manage', 'load-profile', 'alfred-search',
                   'alfred-browse', 'load-settings', 'update-setting',
                   'settings', 'open-help')

        for action in actions:
            if args.get(action):
                methname = 'do_{}'.format(action.replace('-', '_'))
                meth = getattr(self, methname, None)
                if meth:
                    return meth()
                else:
                    break

        raise ValueError('Unknown action : {}'.format(action))

    def do_choose(self):
        """Show a list of subdirectories of ``self.dirpath`` to choose from."""
        dirpath, query = self.dirpath.splitquery()
        log.debug('dirpath=%r,  query=%r', dirpath, query)
        if not os.path.exists(dirpath) or not os.path.isdir(dirpath):
            log.debug('does not exist/not a directory: %r', dirpath)
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

        log.debug('%d folder(s) in %r', len(files), dirpath)
        if files and query:
            log.debug('filtering %d files against %r'. len(files), query)
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
        """Tell Alfred to ask for ``keyword``."""
        return run_trigger('key', arg='{} {} '.format(self.dirpath.abbr_noslash, DELIMITER))
        # return run_alfred(':fzykey {} {} '.format(self.dirpath.abbr_noslash, DELIMITER))

    def do_remove(self):
        """Remove existing folder."""
        profiles = self.wf.settings.get('profiles', {})
        if self.profile in profiles:
            log.debug('Removing profile %r ...', self.profile)
            del profiles[self.profile]
            self.wf.settings['profiles'] = profiles
            self._update_script_filters()
            print('Deleted keyword / Fuzzy Folder')
        else:
            log.debug('No such profile: %r', self.profile)
            print('No such keyword / Fuzzy Folder')

    def do_search(self):
        """Search Fuzzy Folder."""
        if not self.profile:
            return self.do_ad_hoc_search()
        profile = self.wf.settings.get('profiles', {}).get(self.profile)
        if not profile:
            log.debug('Profile not found: %r', self.profile)
            return 1

        root = profile['dirpath']

        scope = profile.get('scope', self.wf.settings.get('defaults',
                            {}).get('scope', SCOPE_FOLDERS))

        min_query = profile.get('min', self.wf.settings.get('defaults',
                                {}).get('min', 1))
        excludes = self.wf.settings.get('defaults', {}).get('excludes', [])
        excludes += profile.get('excludes', [])

        return self._search(root, self.query, scope, min_query, excludes)

    def do_ad_hoc_search(self):
        """Search in directory not stored in a profile."""
        if DELIMITER not in self.query:  # bounce path back to Alfred
            log.debug('No delimiter found')
            search_in_alfred(self.query)
            # run_alfred(self.query)
            # run_alfred(':fzychs {}'.format(Dirpath.dirpath(
            #            self.query.strip()).abbr_slash))
            return 0
        root, query = self._parse_query(self.query)
        log.debug('root=%r,  query=%r', root, query)

        scope = self.wf.settings.get('defaults', {}).get('scope',
                                                         SCOPE_FOLDERS)

        min_query = self.wf.settings.get('defaults', {}).get('min', 1)
        excludes = self.wf.settings.get('defaults', {}).get('excludes', [])

        return self._search(root, query, scope, min_query, excludes)

    def _search(self, root, query, scope, min_query, excludes):
        """Perform search and display results."""
        query = query.split()

        if len(query) > 1:
            mdquery = query[-1]
            query = query[:-1]
        elif len(query):
            mdquery = query[0]
            query = None
        else:
            mdquery = ''
            query = None

        log.debug('mdquery=%r,  query=%r,  scope=%r', mdquery, query, scope)

        if len(mdquery) < min_query or not mdquery:
            self.wf.add_item('Query too short',
                             'minimum length is {}'.format(min_query),
                             valid=False,
                             icon=ICON_WARNING)
            self.wf.send_feedback()
            log.debug('Query too short [min=%d]: %r', min_query, mdquery)
            return 0

        paths = search_in(root, mdquery, scope)

        if excludes:
            paths = filter_excludes(paths, root, excludes)

        if query:
            paths = filter_paths(query, paths, root)

        home = os.path.expanduser('~/')

        if not len(paths):
            self.wf.add_item('No results found',
                             'Try a different query',
                             valid=False,
                             icon=ICON_WARNING)

        for path in paths:
            filename = os.path.basename(path)
            wf.add_item(filename, path.replace(home, '~/'),
                        valid=True, arg=path,
                        uid=path, type='file',
                        icon=path, icontype='fileicon')

        wf.send_feedback()
        log.debug('finished search')
        return 0

    def do_load_profile(self):
        """Load the corresponding profile in Alfred."""
        if self.profile == '0':
            return run_trigger('fuzzy-folders')
        profile = self.wf.settings.get('profiles', {}).get(self.profile)
        log.debug('loading profile %r ...', profile)
        return search_in_alfred(profile['keyword'] + ' ')

    def do_manage(self):
        """Show list of existing profiles."""
        if wf.update_available:
            wf.add_item('A newer version of Fuzzy Folders is available',
                        '↩ or ⇥ to update.',
                        autocomplete='workflow:update',
                        valid=False,
                        icon=ICON_SYNC)

        profiles = self.wf.settings.get('profiles', {})

        if self.query:
            items = profiles.items()
            log.debug('items: %r', items)
            items = self.wf.filter(self.query,
                                   items,
                                   key=lambda t: '{} {}'.format(t[1]['keyword'], t[1]['dirpath']),
                                   match_on=MATCH_ALL ^ MATCH_ALLCHARS)
            profiles = dict(items)

        self.wf.add_item('Default Fuzzy Folder settings',
                         'View / change settings',
                         valid=True,
                         arg="0",
                         icon=ICON_SETTINGS)

        if not profiles:
            self.wf.add_item(
                'No Fuzzy Folders defined',
                "Use the 'Add Fuzzy Folder' File Action to add some",
                valid=False,
                icon=ICON_WARNING)

        for num, profile in profiles.items():
            self.wf.add_item('{} {} {}'.format(profile['keyword'], DELIMITER,
                                                Dirpath.dirpath(profile['dirpath']).abbr_noslash),
                             'View / change settings',
                             valid=True,
                             arg=num,
                             autocomplete=profile['keyword'],
                             icon='icon.png')

        self.wf.send_feedback()

    def do_keyword(self):
        """Choose keyword for folder in Alfred."""
        dirpath, keyword = self._parse_query(self.query)
        log.debug('dirpath=%r,  keyword=%r', dirpath, keyword)

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
                keyword_warnings.append(u"'{}' searches {}".format(
                                        k, Dirpath.dirpath(p).abbr_noslash))
            elif dirpath.abs_noslash == p:
                dirpath_warnings.append(u"Folder already linked to '{}'".format(k))

        if self.query.endswith(DELIMITER):  # user has deleted trailing space
            # back up the file tree
            return run_trigger('choose-folder',
                               arg=Dirpath.dirpath(os.path.dirname(dirpath)).abbr_slash)
            # return run_alfred(':fzychs {}'.format(
            #     Dirpath.dirpath(os.path.dirname(dirpath)).abbr_slash))
            # return self.do_add()
        elif keyword == '':  # no keyword as yet
            if not keyword:
                self.wf.add_item('Enter a keyword for the Folder',
                                 dirpath,
                                 valid=False,
                                 icon=ICON_NOTE)
                for warning in dirpath_warnings:
                    self.wf.add_item(
                        warning,
                        'But you can set multiple keywords per folders',
                        valid=False,
                        icon=ICON_INFO)
                self.wf.send_feedback()
                return 0
        else:  # offer to set keyword
            if profile_exists:
                self.wf.add_item(
                    'This keyword > Fuzzy Folder already exists',
                    u"'{}' already linked to {}".format(
                        keyword,
                        dirpath.abbr_noslash),
                    valid=False,
                    icon=ICON_WARNING)
            else:
                self.wf.add_item(u"Set '{}' as keyword for {}".format(
                    keyword, dirpath.abbr_noslash),
                    dirpath,
                    arg='{} {} {}'.format(dirpath, DELIMITER, keyword),
                    valid=True,
                    icon='icon.png')
                for warning in dirpath_warnings:
                    self.wf.add_item(
                        warning,
                        'But you can set multiple keywords per folders',
                        valid=False,
                        icon=ICON_INFO)
                for warning in keyword_warnings:
                    self.wf.add_item(
                        warning,
                        'But you can use the same keyword for multiple folders',
                        valid=False,
                        icon=ICON_INFO)
            self.wf.send_feedback()

    def do_load_settings(self):
        """Tell Alfred to load profile settings."""
        return run_trigger('set', arg=self.profile)
        # return run_alfred(':fzyset {}'.format(self.profile))

    def do_settings(self):
        """Show file/folder support, min query length for folder."""
        defaults = self.wf.settings.get('defaults', {})
        profile, setting, value = self._parse_settings(self.query)

        if self.query.endswith(DELIMITER):  # trailing space deleted; back up
            return run_trigger('set', arg=profile)
            # return run_alfred(':fzyset {}'.format(profile))

        if not profile:
            return run_trigger('search')
            # return run_alfred('fuzzy ')
            # self.wf.add_item('No Fuzzy Folder specified',
            #                  valid=False,
            #                  icon=ICON_ERROR)
            # self.wf.send_feedback()
            # return 0

        if profile == '0':  # default settings
            conf = defaults.copy()
        else:
            conf = self.wf.settings.get('profiles', {}).get(profile)
        log.debug('conf: %r', conf)

        if not setting:

            kw = conf.get('keyword', 'Fuzzy Folder Defaults')
            path = conf.get('dirpath',
                            # shown for default settings
                            'Overridden by Folder-specific settings')
            self.wf.add_item(kw,
                             path,
                             valid=False,
                             icon='icon.png')

        # Show action to update setting
        if value is not None:
            valuestr = ''
            if value == 0:
                valuestr = 'default'
            if setting == 'min':
                name = 'minimum query length'
                if not valuestr:
                    valuestr = unicode(value)
            elif setting == 'scope':
                name = 'search scope'
                if not valuestr:
                    valuestr = SCOPE_NAMES[value]
            arg = '{} {} min {} {}'.format(profile, DELIMITER, DELIMITER,
                                           value)
            self.wf.add_item('Set {} to {}'.format(name, valuestr),
                             '↩ to update',
                             valid=True,
                             arg=arg,
                             icon=ICON_SETTINGS)
            self.wf.send_feedback()
            return 0

        # Show setting options/ask for query
        elif setting:
            if setting == 'min':
                self.wf.add_item('Enter a minimum query length',
                                 'Enter 0 to use default',
                                 valid=False,
                                 icon=ICON_INFO)
                self.wf.send_feedback()
                return 0
            elif setting == 'scope':
                arg = '{} {} scope {} {}'.format(profile, DELIMITER, DELIMITER, SCOPE_FOLDERS)
                self.wf.add_item('Folders only',
                                 'Only search for folders',
                                 arg=arg,
                                 valid=True,
                                 icon=ICON_SETTINGS)
                arg = '{} {} scope {} {}'.format(profile, DELIMITER, DELIMITER, SCOPE_FILES)
                self.wf.add_item('Files only',
                                 'Only search for files',
                                 arg=arg,
                                 valid=True,
                                 icon=ICON_SETTINGS)
                arg = '{} {} scope {} {}'.format(profile, DELIMITER, DELIMITER, SCOPE_ALL)
                self.wf.add_item('Folders and files',
                                 'Search for folders and files',
                                 arg=arg,
                                 valid=True,
                                 icon=ICON_SETTINGS)
                arg = '{} {} scope {} 0'.format(profile, DELIMITER, DELIMITER)
                self.wf.add_item('Default',
                                 'Use default setting',
                                 arg=arg,
                                 valid=True,
                                 icon=ICON_SETTINGS)
                self.wf.send_feedback()

            else:
                self.wf.add_item('Unknown setting : {}'.format(setting),
                                 'Hit ⌫ to choose again',
                                 valid=False,
                                 icon=ICON_ERROR)
                self.wf.send_feedback()
                return 0

        # Show available settings
        else:
            if 'min' in conf:
                value = conf['min']
            else:
                value = 'default'
            arg = '{} {} min {} '.format(profile, DELIMITER, DELIMITER)
            self.wf.add_item(
                'Minimum query length : {}'.format(value),
                'The last part of your query must be this long to trigger a search',
                valid=False,
                arg=arg,
                autocomplete=arg,
                icon=ICON_SETTINGS)

            if 'scope' in conf:
                value = SCOPE_NAMES[conf['scope']]
            else:
                value = 'default'
            arg = '{} {} scope {} '.format(profile, DELIMITER, DELIMITER)
            self.wf.add_item(
                'Search scope : {}'.format(value),
                'Should results be folders and/or files?',
                valid=False,
                arg=arg,
                autocomplete=arg,
                icon=ICON_SETTINGS)

            self.wf.send_feedback()
        return 0

    def do_update_setting(self):
        """Update profile/default settings from ``query``."""
        profile, setting, value = self._parse_settings(self.query)
        log.debug('setting %s/%s to %r', profile, setting, value)

        if setting not in ('min', 'scope'):
            log.error('Invalid setting: %s', setting)
            print('Invalid setting: %s', setting)
            return 0

        if profile == '0':
            self.wf.settings['defaults'][setting] = value
        else:
            if value == 0:  # reset to default
                if setting in self.wf.settings['profiles'][profile]:
                    del self.wf.settings['profiles'][profile][setting]
            else:
                self.wf.settings['profiles'][profile][setting] = value

        self.wf.settings.save()

        if value == 0:
            value = 'default'
        elif setting == 'scope':
            value = SCOPE_NAMES[value]

        setting = {'min': 'minimum query length',
                   'scope': 'search scope'}.get(setting)

        print('{} set to {}'.format(setting, value))
        return 0

    def do_update(self):
        """Save new/updated Script Filter to info.plist."""
        if not self.query:  # Just do an update
            self._update_script_filters()
            reload_workflow()
            return 0

        dirpath, keyword = self._parse_query(self.query)
        log.debug('dirpath=%r, keyword=%r', dirpath, keyword)
        profiles = self.wf.settings.setdefault('profiles', {})
        log.debug('profiles: %r', profiles)
        if not profiles:
            last = 0
        else:
            last = max([int(s) for s in profiles.keys()])
        log.debug('Last profile: %d', last)
        profile = dict(keyword=keyword, dirpath=dirpath, excludes=[])
        profiles[unicode(last + 1)] = profile  # JSON requires string keys
        self.wf.settings['profiles'] = profiles
        self._update_script_filters()
        print(u"Keyword '{}' searches {}".format(keyword, Dirpath.dirpath(dirpath).abbr_noslash))
        reload_workflow()

    def do_alfred_search(self):
        """Initiate an ad-hoc search in Alfred."""
        dirpath = Dirpath.dirpath(self.query).abbr_noslash
        return run_trigger('search', arg='{} {} '.format(dirpath, DELIMITER))
        # return run_alfred(':fzysrch {} {} '.format(dirpath, DELIMITER))

    # def do_alfred_browse(self):
    #     """Open directory in Alfred."""
    #     return browse_in_alfred(self.dirpath)
    #     # return run_alfred(self.dirpath)

    def do_open_help(self):
        """Open help file in browser."""
        return subprocess.call(['open', self.wf.workflowfile('README.html')])

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
                'queuedelaycustom': 3,  # Auto delay after keypress
                'script': 'python ff.py search "$1" {}'.format(num),
                'subtext': 'Fuzzy search across subdirectories of {}'.format(
                    dirname),
                'title': 'Fuzzy Search {}'.format(dirname),
                'scriptargtype': 1,
                'type': 0,
                'withspace': True
            }
            script_filter['config'] = config
            objects.append(script_filter)
            # set position
            uidata[uid] = {'ypos': float(y_pos)}
            y_pos += YSIZE
            # add connection to Browse in Alfred action
            connections[uid] = ACTIONS

        plist['objects'] = objects
        plist['uidata'] = uidata
        plist['connections'] = connections

        writePlist(plist, plisttemp)
        os.unlink(plistpath)
        os.rename(plisttemp, plistpath)
        os.utime(plistpath, None)

        log.debug('Wrote %d Script Filters to info.plist', len(profiles))

    # def _dirpath_abbr(self, dirpath=None):
    #     """Return attr:`~FuzzyFolders.dirpath` with ``$HOME`` replaced
    #     with ``~/``

    #     """

    #     if not dirpath:
    #         dirpath = self.dirpath
    #     if not dirpath.endswith('/'):
    #         dirpath += '/'
    #     dirpath = dirpath.replace(os.path.expanduser('~/'), '~/')
    #     if dirpath.endswith('/') and dirpath not in ('/', '~/'):
    #         dirpath = dirpath[:-1]
    #     return dirpath

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

    def _parse_settings(self, query):
        """Split ``query`` into ``profile``, ``setting`` and ``value``."""
        profile = setting = value = None
        components = [s.strip() for s in query.split(DELIMITER)]
        log.debug('components: %r', components)
        profile = components[0]
        if len(components) > 1 and components[1]:
            setting = components[1]
        if len(components) > 2 and components[2]:
            value = int(components[2])
        log.debug('profile=%, setting=%r,  value=%r', profile, setting, value)
        return (profile, setting, value)

    def _reset_script_filters(self):
        """Load script filters from `info.plist`."""
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
            log.debug('script: %r', script)
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

        log.debug('%d Script Filters deleted from info.plist', count)
        return script_filters


def main(wf):
    """Run workflow."""
    args = docopt(__doc__, argv=wf.args, version=wf.version)
    log.debug('args: %r', args)
    ff = FuzzyFolders(wf)
    return ff.run(args)


if __name__ == '__main__':
    wf = Workflow(update_settings={'github_slug': 'deanishe/alfred-fuzzyfolders'})
    log = wf.logger
    sys.exit(wf.run(main))
