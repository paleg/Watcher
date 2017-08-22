import os
import sys
import shutil
import subprocess
import pwd, grp

from setuptools.command.install import install
from setuptools import setup, find_packages

import fs_watcher

#class CustomInstallCommand(install):
#    def run(self):
#        install.run(self)
#        current_dir_path = os.path.dirname(os.path.realpath(__file__))
#        confDst = "/etc/watcher.ini"
#        if not os.path.isfile(confDst):
#            confSrc = os.path.join(current_dir_path, "share/etc/watcher.ini")
#            print("Installing default config to {}".format(confDst))
#            shutil.copy2(confSrc, confDst)
#        else:
#            print("{} is already exist, skipping installation".format(confDst))
#        initSystem = os.path.basename(os.readlink("/proc/1/exe"))
#        if initSystem == "systemd":
#            systemdUnit = "watcher.service"
#            systemdSrc = os.path.join(current_dir_path, "share/init", systemdUnit)
#            systemdDst = os.path.join("/lib/systemd/system", systemdUnit)
#            print("Installing systemd unit to {}".format(systemdDst))
#            shutil.copy2(systemdSrc, systemdDst)
#            os.chown(systemdDst, pwd.getpwnam("root").pw_uid, grp.getgrnam("root").gr_gid)
#            os.chmod(systemdDst, 0o644)
#            subprocess.check_output("systemctl daemon-reload", shell=True)
#        else:
#            print("Unknown init system ({}), skipping init script installation".format(initSystem))

debian_changelog = os.path.join(os.getcwd(), os.path.dirname(sys.argv[0]), 'debian/changelog')

debian_template = """\
fs-watcher (%s-0) unstable; urgency=low

  * Latest filesystem watcher release.

 -- Oleg Palij <o.palij@gmail.com>  %s

"""

def debian ():
	from email.utils import formatdate
	with open(debian_changelog, 'w') as w:
		w.write(debian_template % (fs_watcher.__version__, formatdate()))
	print('updated debian/changelog')

if sys.argv[-1] == 'debian':
    debian()
    sys.exit(0)

setup(
    name="fs-watcher",
    version=fs_watcher.__version__.strip(),
    packages=find_packages(),
    data_files=[
        ('share/fs-watcher/etc',  ['debian/watcher.ini']),
        ('share/fs-watcher/init', ['debian/fs-watcher.service',
                                   'debian/fs-watcher.sysvinit',
                                   'debian/fs-watcher.openrc']),
    ],
    # generate platform specific start script
    entry_points={
        'console_scripts': [
            'watcher=fs_watcher.cli:main',
        ]
    },
    setup_requires=["setuptools"],
    install_requires=["future", "pyinotify", "python-daemon", "lockfile", "chardet"],
    url="https://github.com/paleg/Watcher",
    download_url="https://github.com/paleg/Watcher/releases",
    keywords=["inotify", "filesystem", "python", "watcher"],
    maintainer = 'Oleg Palij',
    maintainer_email = 'o.palij@gmail.com',
    platforms='Linux',
    license='MIT',
    classifiers=[
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
    ],
    description="Daemon that watches specified files/folders for changes and fires commands in response to those changes",
    long_description=open('README.rst').read(),
    #cmdclass={'install': CustomInstallCommand},
)
