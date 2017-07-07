"""User behavior definition for load-testing via Locust. Run using tools/load_test.sh.

We expect very low traffic (100-1K qpd for most endpoints). These load tests generate much more
traffic (around 10qps) to stress test the system / simulate traffic spikes.
"""

import json
import os
import random
import re
import time
from urllib import urlencode
import urlparse

from locust import Locust, TaskSet, events, task

from client import Client, HttpException
from data_gen.fake_participant_generator import FakeParticipantGenerator


class _ReportingClient(Client):
  """Wrapper around the API Client which reports request stats to Locust."""
  def request_json(self, path, **kwargs):
    event_data = {'request_type': 'REST', 'name': self._clean_up_url(path)}
    event = None
    try:
      start_seconds = time.time()
      resp = super(_ReportingClient, self).request_json(path, **kwargs)
      event = events.request_success
      event_data['response_length'] = len(json.dumps(resp))
      return resp
    except HttpException as e:
      event = events.request_failure
      event_data['exception'] = e
    finally:
      if event is not None:
        event_data['response_time'] = int(1000 * (time.time() - start_seconds))
        event.fire(**event_data)

  def _clean_up_url(self, path):
    # Replace varying IDs with a placeholder so counts get aggregated.
    name = re.sub('P[0-9]+', ':participant_id', path)

    # Convert absolute URLs to relative.
    strip_prefix = '%s/%s/' % (self.instance, self.base_path)
    if name.startswith(strip_prefix):
      name = name[len(strip_prefix):]
    # Prefix relative URLs with the root path for readability.
    if not name.startswith('http'):
      name = '/' + name

    # Replace query parameters with non-varying placeholders.
    parsed = urlparse.urlparse(name)
    query = urlparse.parse_qs(parsed.query)
    for k in query.keys():
      query[k] = 'X'
    name = parsed._replace(query=urlencode(query)).geturl()

    return name


class _AuthenticatedLocust(Locust):
  """Base for authenticated RDR REST API callers."""
  def __init__(self, *args, **kwargs):
    super(_AuthenticatedLocust, self).__init__(*args, **kwargs)
    creds_file = os.environ['LOCUST_CREDS_FILE']
    instance = os.environ['LOCUST_TARGET_INSTANCE']
    # The "client" field gets copied to TaskSet instances.
    self.client = _ReportingClient(
        creds_file=creds_file, default_instance=instance, parse_cli=False)
    self.participant_generator = FakeParticipantGenerator(self.client)


class HealthProUser(_AuthenticatedLocust):
  """Queries run by HealthPro: look up user by name + dob or ID, and get summaries."""
  weight = 1
  # We (probably over)estimate 100-1000 summary or participant queries/day (per task below).
  min_wait = 10 * 1000
  max_wait = 60 * 1000

  class task_set(TaskSet):
    def __init__(self, *args, **kwargs):
      super(HealthProUser.task_set, self).__init__(*args, **kwargs)

    @task(1)
    def query_summary(self):
      search_params = {
        'hpoId': random.choice(('PITT', 'UNSET', 'COLUMBIA')),
        'desc': 'consentForStudyEnrollmentTime',
        '_count': '1000',
      }
      self.client.request_json('ParticipantSummary?%s' % urlencode(search_params))
