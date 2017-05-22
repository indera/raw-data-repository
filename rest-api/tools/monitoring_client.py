import argparse
import json
import logging
import os
import sys
from oauth2client.client import GoogleCredentials
from oauth2client import client
from googleapiclient.discovery import build

_USER_METRIC_FILTER = 'metric.type = starts_with("logging.googleapis.com/user/")'
_POLICIES_KEY = 'policies'
_METRIC_DESCRIPTORS_KEY = 'metricDescriptors'

PROJECT_MAP = {'pmi-drc-api-test': { 'api_key': 'AIzaSyCAuQdK6L5AU7c1EOhkeJwEw-7oCs5HsiE',
                                     'project_id': '118972441757',
                                     'notification_channel_ids': ['841940086686265891', '7271756574530877070'] },
            'all-of-us-rdr-staging': { 'api_key': 'AIzaSyB3A9zGsvc9DPCdTXleXIs9wHRIRUbfA-E',
                                       'project_id': '261005263653',
                                       'notification_channel_ids': ['1726500439316347724'] },
            'all-of-us-rdr-dryrun': { 'api_key': 'AIzaSyDWsIYuhfLO5CWnTuiw1Bm8m5aSaR8kQQ0',
                                      'project_id': '90017737200',
                                      'notification_channel_ids': ['515929249894770147'] },
            'all-of-us-rdr-stable': { 'api_key': 'AIzaSyBmLhyFlg2q_vxllk27R-3t5ZNzJTf0C40',
                                      'project_id': '812931298053',
                                      'notification_channel_ids': [] },
            'all-of-us-rdr-prod': { 'api_key': 'AIzaSyAUcQj4l-8DfqS5-A_InN7VD8ZN_lLtflU',
                                    'project_id': '106251944765',
                                    'notification_channel_ids': ['771610197803600435', '13127179291565379182']}}

def create_monitoring_client(api_key, credentials):
  discovery_base_url = 'https://monitoring.googleapis.com/$discovery/rest'
  discovery_visibility = 'STACKDRIVER_ALERTING_TRUSTED_TESTER'
  discovery_url = ('%s?labels=%s&key=%s' % (discovery_base_url, discovery_visibility, api_key))
  return build('monitoring', 'v3', discoveryServiceUrl=discovery_url, credentials=credentials)

def make_name(project_id):
  return 'projects/%s' % project_id

def list_policies(policies_api, project_id):
  request = policies_api.list(name=make_name(project_id))
  while request:
    response = request.execute()
    for policy in response.get('alertPolicies', []):
      yield policy
    request = policies_api.list_next(request, response)

def list_metric_descriptors(metric_descriptors_api, project_id):
  request = metric_descriptors_api.list(name=make_name(project_id),
                                        filter=_USER_METRIC_FILTER)
  while request:
    response = request.execute()
    for policy in response.get('metricDescriptors', []):
      yield policy
    request = metric_descriptors_api.list_next(request, response)

def create_policy(policies_api, project_id, policy):
  result = policies_api.create(name=make_name(project_id), body=policy).execute()
  logging.info('Created policy: %s' % result)

def update_policy(policies_api, project_id, policy):
  result = policies_api.patch(name=make_name(project_id), body=policy).execute()
  logging.info('Updated policy: %s' % result)

def read_policies(policy_file):
  if os.path.exists(policy_file):
    with open(policy_file, 'r') as fp:
      policy_json = json.load(fp)
      return policy_json
  else:
    return {}

def write_policies(policy_file, policies, metric_descriptors):
  with open(policy_file, 'w') as fp:
    policy_json = {_POLICIES_KEY: policies, _METRIC_DESCRIPTORS_KEY: metric_descriptors}
    json.dump(policy_json, fp, indent=4)
  logging.info('Wrote %d policies and %d metric descriptors to %s.' % (len(policies), len(metric_descriptors),
                                                                       policy_file))

def create_metric_descriptor(metric_descriptors_api, project_id, metric_descriptor):
  result = metric_descriptors_api.create(name=make_name(project_id), body=metric_descriptor).execute()
  logging.info('Created metric_descriptor: %s' % result)

def main(args):
  logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(levelname)s: %(message)s')
  project_info = PROJECT_MAP.get(args.project)
  if not project_info:
    print 'API key for project %s not found; exiting.' % args.project
    sys.exit(-1)

  credentials = GoogleCredentials.get_application_default()
  monitoring = create_monitoring_client(project_info['api_key'], credentials)
  policies_api = monitoring.projects().alertPolicies()
  metric_descriptors_api = monitoring.projects().metricDescriptors()

  project_id = project_info['project_id']
  existing_policies = list(list_policies(policies_api, project_id))
  existing_metric_descriptors = list(list_metric_descriptors(metric_descriptors_api, project_id))
  policy_json = read_policies(args.policy_file)
  local_policies = policy_json.get(_POLICIES_KEY) or []
  local_metric_descriptors = policy_json.get(_METRIC_DESCRIPTORS_KEY) or []
  if args.update:
    existing_policy_map = {policy['name']: policy for policy in existing_policies}
    existing_descriptor_map = {descriptor['name']: descriptor for descriptor in existing_metric_descriptors}

    for policy in local_policies:
      policy_name = policy.get('name')
      if policy_name:
        existing_policy = existing_policy_map.get(policy_name)
        if not existing_policy:
          logging.info('Policy %s does not exist, creating with new name.', policy_name)
          del policy[policy_name]
          create_policy(policies_api, project_id, policy)
        else:
          if existing_policy == policy:
            logging.info('Policy %s remains unchanged.', policy_name)
          else:
            logging.info('Updating policy %s.', policy_name)
            update_policy(policies_api, project_id, policy)
      else:
        logging.info('Creating policy.')
        create_policy(policies_api, project_id, policy)
    for metric_descriptor in local_metric_descriptors:
      descriptor_name = metric_descriptor.get('name')
      existing_descriptor = existing_descriptor_map.get(descriptor_name)
      if not existing_descriptor:
        logging.info('Descriptor %s does not exist, creating.', descriptor_name)
        create_metric_descriptor(metric_descriptors_api, project_id, metric_descriptor)
      else:
        if existing_descriptor == metric_descriptor:
          logging.info('Descriptor %s remains unchanged.', descriptor_name)
        else:
          logging.warning('Descriptor %s differs in content (%s vs %s); rename to make new descriptor.',
                          descriptor_name, metric_descriptor, existing_descriptor)
    existing_policies = list(list_policies(policies_api, project_id))
    existing_metric_descriptors = list(list_metric_descriptors(metric_descriptors_api, project_id))
  write_policies(args.policy_file, existing_policies, existing_metric_descriptors)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--project',
                      help='The project being used',
                      required=True)
  parser.add_argument('--policy_file',
                      help='A file containing alert policies to import and/or export to',
                      required=True)
  parser.add_argument('--update',
                      help='Specify this if you want to import policies to the file and export ' +
                      'afterwards; do not specify it if you want to solely export',
                      action='store_true')
  main(parser.parse_args())
