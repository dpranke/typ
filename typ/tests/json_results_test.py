# Copyright 2014 Dirk Pranke. All rights reserved.
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



from typ import host_fake
from typ import json_results
from typ import test_case


class FakeArgs(object):
    def __init__(self, builder_name=None, master_name=None, metadata = None,
                 test_results_server=None, test_type = None,
                 write_full_results_to=None):
        self.builder_name = builder_name
        self.master_name = master_name
        self.metadata = metadata or []
        self.test_results_server = test_results_server
        self.test_type = test_type
        self.write_full_results_to = write_full_results_to


class TestWriteFullResultsIfNecessary(test_case.TestCase):

    def test_nothing_written(self):
        host = host_fake.FakeHost()
        args = FakeArgs()
        results = 'empty'
        json_results.write_full_results_if_necessary(args, results, host)
        self.assertEqual(host.written_files, {})

    def test_something_written(self):
        host = host_fake.FakeHost()
        args = FakeArgs(write_full_results_to='/tmp/results.json')
        results = 'empty'
        json_results.write_full_results_if_necessary(args, results, host)
        self.assertEqual(host.read_text_file(args.write_full_results_to),
                         '"empty"\n')
