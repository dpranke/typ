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


class Stats(object):
    def __init__(self, status_format, time_fn, started_time):
        self.fmt = status_format
        self.finished = 0
        self.started = 0
        self.total = 0
        self.started_time = started_time
        self._time = time_fn

    def format(self):
        out = ''
        p = 0
        end = len(self.fmt)
        while p < end:
            c = self.fmt[p]
            if c == '%' and p < end - 1:
                cn = self.fmt[p + 1]
                if cn == 'e':
                    out += '%-5.3f' % (self._time() - self.started_time)
                elif cn == 'f':
                    out += str(self.finished)
                elif cn == 'o':
                    now = self._time()
                    if now > self.started_time:
                        out += '%5.1f' % (self.finished - self.started /
                                          now - self.started_time)
                    else:
                        out += '-'
                elif cn == 'p':
                    out += '%5.1f' % (self.started * 100.0 / self.total)
                elif cn == 'r':
                    out += str(self.started - self.finished)
                elif cn == 's':
                    out += str(self.started)
                elif cn == 't':
                    out += str(self.total)
                elif cn == '%%':
                    out += '%'
                else:
                    out += cn
                p += 2
            else:
                out += c
                p += 1
        return out
