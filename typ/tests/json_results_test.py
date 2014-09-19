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

class TestUploadFullResultsIfNecessary(test_case.TestCase):

    def test_no_upload(self):
        host = host_fake.FakeHost()
        args = FakeArgs()
        res, msg = json_results.upload_full_results_if_necessary(args, None,
                                                                 host)
        self.assertEqual(res, False)
        self.assertEqual(msg, '')

    def test_basic_upload(self):
        host = host_fake.FakeHost()
        args = FakeArgs(builder_name='fake_builder_name',
                        master_name='fake_master',
                        test_results_server='localhost',
                        test_type='fake_test_type')
        results = {'foo': 'bar'}
        res, msg = json_results.upload_full_results_if_necessary(args, results,
                                                                 host)
        self.assertEqual(res, False)
        self.assertEqual(msg, '')

        self.assertEqual(len(host.fetches), 1)
        url, data, headers, _ = host.fetches[0]
        ctype = 'multipart/form-data; boundary=-M-A-G-I-C---B-O-U-N-D-A-R-Y-'
        self.assertEqual(headers, {'Content-Type': ctype})
        self.assertEqual(
            data,
            ('---M-A-G-I-C---B-O-U-N-D-A-R-Y-\r\n'
             'Content-Disposition: form-data; name="builder"\r\n'
             '\r\n'
             'fake_builder_name\r\n'
             '---M-A-G-I-C---B-O-U-N-D-A-R-Y-\r\n'
             'Content-Disposition: form-data; name="master"\r\n'
             '\r\n'
             'fake_master\r\n'
             '---M-A-G-I-C---B-O-U-N-D-A-R-Y-\r\n'
             'Content-Disposition: form-data; name="testtype"\r\n'
             '\r\n'
             'fake_test_type\r\n'
             '---M-A-G-I-C---B-O-U-N-D-A-R-Y-\r\n'
             'Content-Disposition: form-data; name="file"; filename="full_results.json"\r\n'
             'Content-Type: application/json\r\n'
             '\r\n'
             '{"foo": "bar"}\r\n'
             '---M-A-G-I-C---B-O-U-N-D-A-R-Y---\r\n'))
