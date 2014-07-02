# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from setuptools import setup
import setuptools

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'typ', 'VERSION')) as fp:
    version = fp.read().strip()

with open(os.path.join(here, 'README.md')) as fp:
    readme = fp.read().strip()

readme_lines = readme.splitlines()

setup(
    name='typ',
    packages=['typ'],
    entry_points={
        'console_scripts': [
            'typ=typ:main',
        ]
    },
    version=version,
    description=readme_lines[3],
    long_description='\n'.join(readme_lines[4:]),
    url='https://github.com/dpranke/typ',
    license='Apache',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Testing',
    ],
)
