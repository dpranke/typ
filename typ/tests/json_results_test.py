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

from typ import json_results


class TestMakeUploadRequest(unittest.TestCase):

    def test_basic_upload(self):
        results = {'foo': 'bar'}
        url, content_type, data = json_results.make_upload_request(
            'localhost', 'fake_builder_name', 'fake_master', 'fake_test_type',
            results)

        self.assertEqual(
            content_type,
            'multipart/form-data; boundary=-M-A-G-I-C---B-O-U-N-D-A-R-Y-')

        self.assertEqual(url, 'http://localhost/testfile/upload')
        self.assertMultiLineEqual(
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


class TestMakeFullResults(unittest.TestCase):
    maxDiff = 2048

    def test_basic(self):
        test_names = ['foo_test.FooTest.test_fail',
                      'foo_test.FooTest.test_pass',
                      'foo_test.FooTest.test_skip']
        result = unittest.TestResult()
        result.successes = [('foo_test.FooTest.test_pass', '')]
        result.errors = [('foo_test.FooTest.test_fail', 'failure')]

        full_results = json_results.make_full_results(
            ['foo=bar'], 0, test_names, [result])
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
