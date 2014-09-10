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

import json
import time
import unittest
import urllib2


def write_full_results_if_necessary(args, test_results):
    if not args.write_full_results_to:
        return

    with open(args.write_full_results_to, 'w') as fp:
        json.dump(test_results, fp, indent=2)
        fp.write("\n")


def upload_full_results_if_necessary(args, test_results):
    if not args.test_results_server:
        return False, ''

    url = 'http://%s/testfile/upload' % args.test_results_server
    attrs = [('builder', args.builder_name),
             ('master', args.master_name),
             ('testtype', args.test_type)]
    content_type, data = _encode_multipart_form_data(attrs, test_results)
    return _upload_data(url, data, content_type)


TEST_SEPARATOR = '.'


def full_results(args, test_names, results):
    """Convert the unittest results to the Chromium JSON test result format.

    See http://www.chromium.org/developers/the-json-test-results-format
    """

    test_results = {}
    test_results['interrupted'] = False
    test_results['path_delimiter'] = TEST_SEPARATOR
    test_results['version'] = 3
    test_results['seconds_since_epoch'] = time.time()
    for md in args.metadata:
        key, val = md.split('=', 1)
        full_results[key] = val

    # TODO(dpranke): Handle skipped tests as well.

    num_failures = num_failures_after_retries(results)
    test_results['num_failures_by_type'] = {
        'FAIL': num_failures,
        'PASS': len(test_names) - num_failures,
    }

    sets_of_passing_test_names = map(passing_test_names, results)
    sets_of_failing_test_names = map(functools.partial(failed_test_names, suite),
                                     results)

    # Handle tests skipped via the unittest skip decorators (like skipUnless).
    # TODO: We still need a way for the caller to add user-skipped tests.
    skipped_tests = (set(all_test_names) - sets_of_passing_test_names[0]
                                         - sets_of_failing_test_names[0])

    num_tests = len(all_test_names)
    num_failures = num_failures_after_retries(suite, results)
    num_skips = len(skipped_tests)
    num_passes = num_tests - num_failures - num_skips
    full_results['num_failures_by_type'] = {
        'FAIL': num_failures,
        'PASS': num_passes,
        'SKIP': num_skips,
    }

    test_results['tests'] = {}

    for test_name in test_names:
        if test_name in skipped_tests:
            value = {
                'expected': 'SKIP',
                'actual': 'SKIP',
            }
        else:
            value = {
                'expected': 'PASS',
                'actual': actual_results_for_test(test_name,
                                                  sets_of_failing_test_names,
                                                  sets_of_passing_test_names),
            }
            if value['actual'].endswith('FAIL'):
                value['is_unexpected'] = True
            _add_path_to_trie(full_results['tests'], test_name, value)

    return test_results


def actual_results_for_test(test_name, sets_of_failing_test_names,
                            sets_of_passing_test_names):
    actuals = []
    for retry_num in range(len(sets_of_failing_test_names)):
        if test_name in sets_of_failing_test_names[retry_num]:
            actuals.append('FAIL')
        elif test_name in sets_of_passing_test_names[retry_num]:
            assert ((retry_num == 0) or
                    (test_name in sets_of_failing_test_names[retry_num - 1])), (
                      'We should not have run a test that did not fail '
                      'on the previous run.')
            actuals.append('PASS')

    assert actuals, 'We did not find any result data for %s.' % test_name
    return ' '.join(actuals)


def exit_code_from_full_results(test_results):
    return 1 if test_results['num_failures_by_type']['FAIL'] else 0


def all_test_names(suite):
    test_names = []
    # _tests is protected  pylint: disable=W0212
    for test in suite._tests:
        if isinstance(test, unittest.suite.TestSuite):
            test_names.extend(all_test_names(test))
        else:
            test_names.append(test.id())
    return test_names


def num_failures_after_retries(results):
    return len(failed_test_names(results[-1]))


def failed_test_names(result):
  failed_test_names = set()
  for test, error in result.failures + result.errors:
    if isinstance(test, unittest.TestCase):
      failed_test_names.add(test.id())
    elif isinstance(test, unittest.suite._ErrorHolder):  # pylint: disable=W0212
      # If there's an error in setUpClass or setUpModule, unittest gives us an
      # _ErrorHolder object. We can parse the object's id for the class or
      # module that failed, then find all tests in that class or module.
      match = re.match('setUp[a-zA-Z]+ \\((.+)\\)', test.id())
      assert match, "Don't know how to retry after this error:\n%s" % error
      module_or_class = match.groups()[0]
      failed_test_names |= _find_children(module_or_class,
                                          all_test_names(suite))
    else:
      assert False, 'Unknown test type: %s' % test.__class__
  return failed_test_names


def _find_children(parent, potential_children):
  children = set()
  parent_name_parts = parent.split('.')
  for potential_child in potential_children:
    child_name_parts = potential_child.split('.')
    if parent_name_parts == child_name_parts[:len(parent_name_parts)]:
      children.add(potential_child)
  return children


def passing_test_names(result):
    return set(test for test, _ in result.successes)


def _add_path_to_trie(trie, path, value):
    if TEST_SEPARATOR not in path:
        trie[path] = value
        return
    directory, rest = path.split(TEST_SEPARATOR, 1)
    if directory not in trie:
        trie[directory] = {}
    _add_path_to_trie(trie[directory], rest, value)


def _encode_multipart_form_data(attrs, test_results):
    # Cloned from webkitpy/common/net/file_uploader.py
    BOUNDARY = '-M-A-G-I-C---B-O-U-N-D-A-R-Y-'
    CRLF = '\r\n'
    lines = []

    for key, value in attrs:
        lines.append('--' + BOUNDARY)
        lines.append('Content-Disposition: form-data; name="%s"' % key)
        lines.append('')
        lines.append(value)

    lines.append('--' + BOUNDARY)
    lines.append('Content-Disposition: form-data; name="file"; '
                 'filename="full_results.json"')
    lines.append('Content-Type: application/json')
    lines.append('')
    lines.append(json.dumps(test_results))

    lines.append('--' + BOUNDARY + '--')
    lines.append('')
    body = CRLF.join(lines)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body


def _upload_data(url, data, content_type):
    request = urllib2.Request(url, data, {'Content-Type': content_type})
    try:
        response = urllib2.urlopen(request)
        if response.code == 200:
            return False, ''
        return True, ('Uploading the JSON results failed with %d: "%s"' %
                      (response.code, response.read()))
    except Exception as e:
        return True, 'Uploading the JSON results raised "%s"\n' % str(e)
