#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IPython -- An enhanced Interactive Python

The actual ipython script to be installed with 'python3 setup.py install' is
in './scripts' directory. This file is here (ipython source root directory)
to facilitate non-root 'zero-installation' (just copy the source tree
somewhere and run ipython.py) and development. """

#-----------------------------------------------------------------------------
#  Copyright (c) 2012, IPython Development Team.
#
#  Distributed under the terms of the Modified BSD License.
#
#  The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

import importlib.machinery
import logging
import os
import sys
import warnings

from lib2to3 import refactor


#-----------------------------------------------------------------------------
# Logging
#-----------------------------------------------------------------------------

# Uncomment to print debug messages:
# logging.basicConfig(level='DEBUG')


#-----------------------------------------------------------------------------
# Classes
#-----------------------------------------------------------------------------

class Auto2to3FileFinder(importlib.machinery.FileFinder):
    """File finder for source types ('.py') which automatically
    runs the 2to3 refactoring tool on import.

    To enable, run::

        path_hook = Auto2to3FileFinder.predicated_path_hook(predicate, refactoring_tool)
        sys.path_hooks.insert(0, path_hook)
        sys.import_path_cache.clear()

    Parameters
    ----------
    predicate : callable, as predicate(path)
        The 2to3 file finder restricts its operations only to directories
        for which the predicate is satisfied (i.e., `predicate(path)`
        evalates to True).
    refactoring_tool : instance of `lib2to3.refactor.RefactoringTool`
        The 2to3 refactoring tool passed to `Auto2to3SourceFileLoader`.
    """

    @classmethod
    def predicated_path_hook(cls, predicate, *loader_details):
        """A class method whch returns a closure to use on sys.path_hook."""
        def predicated_path_hook_for_FileFinder(path):
            """path hook for FileFinder"""
            if not os.path.isdir(path):
                raise ImportError("only directories are supported", path=path)
            if not predicate(path):
                raise ImportError("predicate not satisfied", path=path)
            return cls(path, *loader_details)
        return predicated_path_hook_for_FileFinder

    def __init__(self, path, refactoring_tool):
        logger = logging.getLogger('Auto2to3FileFinder')
        logger.debug("Processing %s" % path)
        auto2to3 = (Auto2to3SourceFileLoader.loader(refactoring_tool),
                    importlib.machinery.SOURCE_SUFFIXES)
        super().__init__(path, auto2to3)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.path)

class Auto2to3SourceFileLoader(importlib.machinery.SourceFileLoader):
    """Source file loader which runs source code through 2to3.

    Initial source loading will be _very_ slow, but results are cached
    so future imports will be faster.

    The cached source code is stored in the `__pycache__` directory with
    a `.ipy2to3.py` suffix.
    """

    @classmethod
    def loader(cls, *details):
        """A class method returning a closure for use as a loader."""
        def loader_for_Auto2to3SourceFileLoader(fullname, path):
            return cls(fullname, path, *details)
        return loader_for_Auto2to3SourceFileLoader

    def __init__(self, fullname, path, refactoring_tool):
        """Initialize the source file loader.

         - fullname and path are as in SourceFileLoader.
         - refactoring_tool is an instance of lib2to3.RefactoringTool
         """
        super().__init__(fullname, path)
        self.original_path = path
        self.refactoring_tool = refactoring_tool
        self.logger = logging.getLogger('Auto2to3SourceFileLoader')
        self.logger.debug('Initialize: %s (%s)' % (fullname, path))

    def _2to3_cache_path(self, path):
        """Path to the cache file (PACKAGE/__pycache__/NAME.ipy2to3.py)"""
        head, tail = os.path.split(path)
        base_filename, sep, tail = tail.partition('.')
        tag = 'ipy2to3'
        filename = ''.join([base_filename, sep, tag, sep, tail])
        return os.path.join(head, '__pycache__', filename)

    def _refactor_2to3(self, path):
        """Run the module through 2to3, returning a string of code and encoding."""
        # self.logger.debug('Refactoring: %s' % path)
        source, encoding = self.refactoring_tool._read_python_source(path)

        source += '\n' # Silence certain parse errors.
        tree = self.refactoring_tool.refactor_string(source, path)
        return str(tree)[:-1], encoding # Take off the '\n' added earlier.

    def _load_cached_2to3(self, path, cache):
        """Load the cached 2to3 source.

        Returns None if the cache is stale or missing.
        """
        try:
            cache_stats = os.stat(cache)
            source_stats = os.stat(path)
        except FileNotFoundError:
            self.logger.debug('Cache miss: %s' % cache)
            return None

        if cache_stats.st_mtime <= source_stats.st_mtime:
            self.logger.debug('Cache miss (stale): %s' % cache)
            return None

        self.logger.debug("Cache hit: %s" % cache)
        return super().get_data(cache)

    def get_data(self, path):
        """Load a file from disk, running source code through 2to3."""

        if path == self.original_path:
            cache = self._2to3_cache_path(path)
            data = self._load_cached_2to3(path, cache)
            if data is None:
                output, encoding = self._refactor_2to3(path)
                data = bytearray(output, encoding or sys.getdefaultencoding())
                self.set_data(cache, data)
            return data

        else:
            return super().get_data(path)

    def load_module(self, fullname):
        """Load the module."""
        self.logger.debug('Loading module: %s' % fullname)
        path = self.get_filename(fullname)
        module = self._load_module(fullname, sourceless=True)
        module.__file__ = self._2to3_cache_path(path)
        return module


#-----------------------------------------------------------------------------
# 2to3 refactoring setup
#-----------------------------------------------------------------------------

def build_fixer_names(exclude_fixers=None):
    """Build a list of required fixers."""
    fixer_names = refactor.get_fixers_from_package('lib2to3.fixes')
    if exclude_fixers:
        for fixer_name in exclude_fixers:
            if fixer_name not in fixer_names:
                warnings.warn("Excluded fixer %s not found" % fixer_name)
            else:
                fixer_names.remove(fixer_name)
    return fixer_names

# Excluded fixers from setup.py
exclude_fixers = [
    'lib2to3.fixes.fix_apply',
    'lib2to3.fixes.fix_except',
    'lib2to3.fixes.fix_has_key',
    'lib2to3.fixes.fix_next',
    'lib2to3.fixes.fix_repr',
    'lib2to3.fixes.fix_tuple_params',
    ]

fixer_names = build_fixer_names(exclude_fixers)
refactoring_tool = refactor.RefactoringTool(fixer_names)

# Ensure that the imported IPython is the local one, not a system-wide one.

this_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, this_dir)

def predicate(path):
    """Match this directory and its subdirectories."""
    abspath = os.path.abspath(path)
    return abspath == this_dir or abspath.startswith(this_dir + os.path.sep)

path_hook = Auto2to3FileFinder.predicated_path_hook(predicate, refactoring_tool)
sys.path_hooks.insert(0, path_hook)

# Since we update the list of path hooks, also clear the cache.
sys.path_importer_cache.clear()

# For debuging, mimic running `import IPython`:
# finder = path_hook(this_dir)
# loader = finder.find_module('IPython')
# IPython = loader.load_module('IPython')


#-----------------------------------------------------------------------------
# Launch IPython
#-----------------------------------------------------------------------------

from IPython.frontend.terminal.ipapp import launch_new_instance
launch_new_instance()
