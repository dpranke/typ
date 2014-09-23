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

import unittest

from typ.fakes import host_fake
from typ import json_results
from typ import test_case
from typ import tester


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
        self.assertEqual(url, 'http://localhost/testfile/upload')
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
             'Content-Disposition: form-data; name="file"; '
             'filename="full_results.json"\r\n'
             'Content-Type: application/json\r\n'
             '\r\n'
             '{"foo": "bar"}\r\n'
             '---M-A-G-I-C---B-O-U-N-D-A-R-Y---\r\n'))
        self.assertEqual(headers, {'Content-Type': ctype})

    def test_upload_fails(self):
        host = host_fake.FakeHost()
        url = 'http://localhost/testfile/upload'
        host.fetch_responses[url] = host_fake.FakeResponse('Not Authorized',
                                                           url, 404)
        args = FakeArgs(builder_name='fake_builder_name',
                        master_name='fake_master',
                        test_results_server='localhost',
                        test_type='fake_test_type')
        results = {'foo': 'bar'}
        res, msg = json_results.upload_full_results_if_necessary(args, results,
                                                                 host)
        self.assertEqual(res, True)
        self.assertEqual(msg, 'Uploading the JSON results failed with '
                              '404: "Not Authorized"')


    def test_upload_raises(self):
        host = host_fake.FakeHost()
        url = 'http://localhost/testfile/upload'

        def raiser(*args):
            raise ValueError('bad arg')

        host.fetch = raiser

        args = FakeArgs(builder_name='fake_builder_name',
                        master_name='fake_master',
                        test_results_server='localhost',
                        test_type='fake_test_type')
        results = {'foo': 'bar'}
        res, msg = json_results.upload_full_results_if_necessary(args, results,
                                                                 host)
        self.assertEqual(res, True)
        self.assertEqual(msg, 'Uploading the JSON results raised "bad arg"\n')


class TestFullResults(test_case.TestCase):
    maxDiff = 2048

    def test_basic(self):
        args = FakeArgs(metadata=['foo=bar'])
        host = host_fake.FakeHost()
        test_names = ['foo_test.FooTest.test_fail',
                      'foo_test.FooTest.test_pass',
                      'foo_test.FooTest.test_skip']
        result = tester.TestResult()
        result.successes = [('foo_test.FooTest.test_pass', '')]
        result.errors = [('foo_test.FooTest.test_fail', 'failure')]

        full_results = json_results.full_results(args, test_names, [result],
                                                 host)
        expected_full_results = {
            'foo': 'bar',
            'interrupted': False,
            'num_failures_by_type': {
                'FAIL': 1,
                'PASS': 1,
                'SKIP': 1},
            'path_delimiter': '.',
            'seconds_since_epoch': 0,
            'tests': {
                'foo_test': {
                    'FooTest': {
                        'test_fail': {
                            'expected': 'PASS',
                            'actual': 'FAIL',
                            'is_unexpected': True},
                        'test_pass': {
                            'expected': 'PASS',
                            'actual': 'PASS'},
                        'test_skip': {
                            'expected': 'SKIP',
                            'actual': 'SKIP'}}}},
            'version': 3}
        self.assertEqual(full_results, expected_full_results)


class _TestCase(unittest.TestCase):
    def test_foo(self):
        pass

class TestAllTestNames(test_case.TestCase):
    def test_basic(self):
        suite1 = unittest.TestSuite()
        suite2 = unittest.TestSuite()

        suite2.addTest(_TestCase('test_foo'))
        suite1.addTest(suite2)

        test_names = json_results.all_test_names(suite1)
        self.assertEqual(test_names,
                         ['typ.tests.json_results_test._TestCase.test_foo'])
