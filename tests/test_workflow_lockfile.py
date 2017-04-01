#!/usr/bin/env python
# encoding: utf-8
#
# Copyright (c) 2017 Dean Jackson <deanishe@deanishe.net>
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2017-04-01
#

"""Test LockFile functionality."""

from __future__ import print_function

from collections import namedtuple
from multiprocessing import Pool
import os
import shutil
import subprocess
import tempfile

import pytest

from workflow.workflow import AcquisitionError, LockFile, Settings


TEMPFILE = 'tempfile.{0}.txt'.format(os.getpid())
LOCKFILE = TEMPFILE + '.lock'


Paths = namedtuple('Paths', 'testfile lockfile')


@pytest.fixture(scope='function')
def paths(request):
    """Ensure `info.plist` exists in the working directory."""
    tempdir = tempfile.mkdtemp()
    testfile = os.path.join(tempdir, 'myfile.txt')

    def rm():
        shutil.rmtree(tempdir)

    request.addfinalizer(rm)

    return Paths(testfile, testfile + '.lock')


def test_lockfile_created(paths):
    """Lock file created and deleted."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    with LockFile(paths.testfile, timeout=0.2) as lock:
        assert lock.locked
        assert os.path.exists(paths.lockfile)

    assert not os.path.exists(paths.lockfile)


def test_lockfile_contains_pid(paths):
    """Lockfile contains process PID."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    with LockFile(paths.testfile, timeout=0.2):
        with open(paths.lockfile) as fp:
            s = fp.read()

    assert s == str(os.getpid())


def test_invalid_lockfile_removed(paths):
    """Invalid lockfile removed."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    # create invalid lock file
    with open(paths.lockfile, 'wb') as fp:
        fp.write("dean woz 'ere!")

    # the above invalid lockfile should be removed and
    # replaced with one containing this process's PID
    with LockFile(paths.testfile, timeout=0.2):
        with open(paths.lockfile) as fp:
            s = fp.read()

    assert s == str(os.getpid())


def test_stale_lockfile_removed(paths):
    """Stale lockfile removed."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    p = subprocess.Popen('true')
    pid = p.pid
    p.wait()
    # create invalid lock file
    with open(paths.lockfile, 'wb') as fp:
        fp.write(str(pid))

    # the above invalid lockfile should be removed and
    # replaced with one containing this process's PID
    with LockFile(paths.testfile, timeout=0.2):
        with open(paths.lockfile) as fp:
            s = fp.read()

    assert s == str(os.getpid())


def test_sequential_access(paths):
    """Sequential access to locked file."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    lock = LockFile(paths.testfile, 0.2)

    with lock:
        assert lock.locked
        assert not lock.acquire(False)
        with pytest.raises(AcquisitionError):
            lock.acquire(True)

    assert not os.path.exists(paths.lockfile)


def _write_test_data(args):
    """Write 10 lines to the test file."""
    paths, data = args
    for i in range(10):
        with LockFile(paths.testfile, 0.5) as lock:
            assert lock.locked
            with open(paths.testfile, 'a') as fp:
                fp.write(data + '\n')


def test_concurrent_access(paths):
    """Concurrent access to locked file is serialised."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    # Create a pool of threads that each write a line
    # of 20 digits to the locked file.
    # Then verify that each line of the file only
    # consists of one character (i.e. writes do no overlap)
    lock = LockFile(paths.testfile, 0.5)

    pool = Pool(5)
    pool.map(_write_test_data, [(paths, str(i) * 20) for i in range(1, 6)])

    assert not lock.locked
    assert not os.path.exists(paths.lockfile)

    with open(paths.testfile) as fp:
        lines = [l.strip() for l in fp.readlines()]

    for line in lines:
        assert len(set(line)) == 1


def _write_settings(args):
    """Write a new value to the Settings."""
    paths, key, value = args
    s = Settings(paths.testfile)
    s[key] = value
    print('Settings[{0}] = {1}'.format(key, value))


def test_concurrent_settings(paths):
    """Concurrent access to Settings is serialised."""
    assert not os.path.exists(paths.testfile)
    assert not os.path.exists(paths.lockfile)

    defaults = {'foo': 'bar'}
    # initialise file
    Settings(paths.testfile, defaults)

    data = [(paths, 'thread_{0}'.format(i), 'value_{0}'.format(i))
            for i in range(1, 6)]

    pool = Pool(5)
    pool.map(_write_settings, data)

    # Check settings file is still valid JSON
    # and that *something* was added to it.
    # The writing processes will have trampled
    # over each other, so there's no way to know
    # which one won and wrote its value.
    s = Settings(paths.testfile)
    assert s['foo'] == 'bar'
    assert len(s) > 1


if __name__ == '__main__':  # pragma: no cover
    pytest.main([__file__])
