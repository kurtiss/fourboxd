#!/usr/bin/env python
# encoding: utf-8
"""
setup.py
"""

from setuptools import setup, find_packages
import os

MODNAME = "fourboxd"

execfile(os.path.join('src', MODNAME, 'version.py'))

setup(
    name = MODNAME,
    version = VERSION,
    description = MODNAME,
    author = 'Kurtiss Hare',
    author_email = 'kurtiss@gmail.com',
    url = 'http://www.github.com/kurtiss/' + MODNAME,
    packages = find_packages('src'),
    package_dir = {'' : 'src'},
    scripts = [
        'src/scripts/fourboxdsync'
    ],
    classifiers = [
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    install_requires = [
        'Unidecode==0.04.17',
        'beautifulsoup4==4.3.2',
        'fourboxd==2015.04.17',
        'foursquare==2015.02.02',
        'more-itertools==2.2',
        'python-slugify==1.1.2',
        'requests==2.6.0',
        'six==1.9.0',
        'wsgiref==0.1.2'
    ],
    zip_safe = False
)