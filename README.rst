filesystem watcher
==================

.. image:: https://img.shields.io/pypi/v/fs-watcher.svg?style=flat-square
    :target: https://warehouse.python.org/project/fs-watcher/
    :alt: fs-watcher on PyPI

.. image:: https://img.shields.io/pypi/l/fs-watcher.svg?style=flat-square
    :target: https://warehouse.python.org/project/fs-watcher/
    :alt: fs-watcher on PyPI

.. image:: https://img.shields.io/github/issues/paleg/Watcher.svg?style=flat-square
    :target: https://github.com/paleg/Watcher/issues
    :alt: GitHub issues for Watcher

|

``Watcher`` is a daemon that watches specified files/folders for changes and
fires commands in response to those changes. It is similar to
incron_, however, configuration uses a simpler
to read ini file instead of a plain text file. Unlike incron it can also
recursively monitor directories.

It's written in Python, making it easier to hack.

* `Source on GitHub <https://github.com/paleg/Watcher>`_
* `Packages on PyPI <https://warehouse.python.org/project/fs-watcher/>`_

This fork is a rewritting of the code using python-daemon implementation of PEP3143_ with additional features:

* async commands executing which allows several copies of command can be executed simultaneously for single job
* capturing command output to separate log file
* exclude watching files by regular expression
* perform actions on successful/failure command completion.

Requirements
------------

``Watcher`` supports both Python 2.7 and Python 3.x. It has following dependencies which can be installed with your package manager or `pip`:

* pyinotify_
* python-daemon_
* lockfile_
* chardet_
* future_

To install dependencies on Debian:

.. code-block:: bash

    sudo apt-get install python-pyinotify python-daemon python-lockfile python-chardet python-future

.. code-block:: bash

    sudo apt-get install python3-pyinotify python3-daemon python3-lockfile python3-chardet python3-future

To install dependencies on Gentoo:

.. code-block:: bash

    emerge -av dev-python/pyinotify dev-python/python-daemon dev-python/lockfile dev-python/chardet dev-python/future

pip_ will install dependencies automatically.

Installation
------------

Debian
~~~~~~

Download latest deb package from `GitHub releases page <https://github.com/paleg/Watcher/releases>`_ and install it with ``dpkg``.

.. code-block:: bash

    sudo dpkg -i fs-watcher_X.Y.Z-0_all.deb

In addition to ``Watcher`` itself, it will install:

* sample configuration file to ``/etc/watcher.ini``
* systemd service ``fs-watcher`` (in disabled state).

To start using ``Watcher`` you must change ``/etc/watcher.ini`` to suit your needs and enable/start ``fs-watcher`` service.

Pip
~~~
System-wide using pip_:

.. code-block:: bash

    sudo pip install fs-watcher

.. code-block:: bash

    sudo pip3 install fs-watcher


This command will install:

* Python modules for ``Watcher``
* sample configuration file
* samples of startup scripts
* executable to start ``Watcher``

Use following command to check exact locations:

.. code-block:: bash

    pip show -f fs-watcher

There are samples of startup scripts. Use your init system manual to install them properly. Check/fix path to ``Watcher`` executable in samples before using, by default it is assumed to be ``/usr/sbin/watcher``.

For systemd:

.. code-block:: bash

    cp share/init/fs-watcher.service /etc/systemd/system/fs-watcher.service
    systemctl daemon-reload
    systemctl enable fs-watcher
    systemctl start fs-watcher

For SysV:

.. code-block:: bash

    cp share/init/fs-watcher.sysvinit /etc/init.d/fs-watcher
    update-rc.d fs-watcher defaults
    /etc/init.d/fs-watcher start

For OpenRC:

.. code-block:: bash

    cp share/init/fs-watcher.openrc /etc/init.d/fs-watcher
    rc-update add fs-watcher default
    /etc/init.d/fs-watcher start


Configuration
-------------

Check provided `watcher.ini`_ file for an example job configuration. The config file should reside in ``/etc/watcher.ini`` or ``~/.watcher.ini``. You can also specify the path to the config file as a command line parameter using the ``--config`` option.

If you edit the ini file you must restart the daemon for it to reload the configuration.

Usage
-----

.. code::

	usage: watcher [-h] [--version] [-c CONFIG] [-v] {start,stop,restart,debug}

	positional arguments:
	  {start,stop,restart,debug}
							What to do.

	optional arguments:
	  -h, --help            show this help message and exit
	  --version             show program's version number and exit
	  -c CONFIG, --config CONFIG
							Path to the config file (default: None)
	  -v, --verbose         verbose output

Debug mode
~~~~~~~~~~
You can start ``Watcher`` with `debug` positional argument to prevent it from forking to the background and log messages to stdout:

.. code-block:: bash

	watcher debug

.. _incron: http://incron.aiken.cz/
.. _PEP3143: http://legacy.python.org/dev/peps/pep-3143/
.. _pyinotify: http://github.com/seb-m/pyinotify
.. _python-daemon: https://alioth.debian.org/projects/python-daemon/
.. _lockfile: https://launchpad.net/pylockfile
.. _chardet: https://chardet.github.io/
.. _future: https://pypi.python.org/pypi/future
.. _pip: https://pip.readthedocs.org/
.. _watcher.ini: /debian/watcher.ini
