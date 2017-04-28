import argparse
import json
import logging
import os
import sys
from oauth2client.client import GoogleCredentials
from oauth2client import client
from googleapiclient.discovery import build

PROJECT_MAP = {'pmi-drc-api-test': ('AIzaSyCAuQdK6L5AU7c1EOhkeJwEw-7oCs5HsiE', '118972441757'),
            'all-of-us-rdr-staging': ('AIzaSyB3A9zGsvc9DPCdTXleXIs9wHRIRUbfA-E', '261005263653'),
            'all-of-us-rdr-dryrun': ('AIzaSyDWsIYuhfLO5CWnTuiw1Bm8m5aSaR8kQQ0', '90017737200'),
            'all-of-us-rdr-stable': ('AIzaSyBmLhyFlg2q_vxllk27R-3t5ZNzJTf0C40', '812931298053'),
            'all-of-us-rdr-prod': ('AIzaSyAUcQj4l-8DfqS5-A_InN7VD8ZN_lLtflU', '106251944765')}

def create_monitoring_client(api_key, credentials):
   discovery_base_url='https://monitoring.googleapis.com/$discovery/rest'
   discovery_visibility='STACKDRIVER_ALERTING_TRUSTED_TESTER'
   discovery_url=('%s?labels=%s&key=%s' %
                  (discovery_base_url, discovery_visibility, api_key))
   return build(
        'monitoring',
        'v3',
        discoveryServiceUrl=discovery_url,
        credentials=credentials)

def make_name(project_id):
  return 'projects/%s' % project_id

def list_policies(policies_api, project_id):
  request = policies_api.list(name=make_name(project_id))
  while request:
    response = request.execute()
    for policy in response.get('alertPolicies', []):
      yield policy
    request = policies_api.list_next(request, response)

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
      return policy_json['policies']
  else:
    return []

def write_policies(policy_file, policies):
  with open(policy_file, 'w') as fp:
    policy_json = { 'policies': policies }
    json.dump(policy_json, fp, indent=4)
  logging.info('Wrote %d policies to %s.' % (len(policies), policy_file))

def main(args):
  logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(levelname)s: %(message)s')
  project_info = PROJECT_MAP.get(args.project)
  if not project_info:
    print 'API key for project %s not found; exiting.' % args.project
    sys.exit(-1)

  credentials = GoogleCredentials.get_application_default()
  monitoring = create_monitoring_client(project_info[0], credentials)
  policies_api = monitoring.projects().alertPolicies()

  project_id = project_info[1]
  existing_policies = list(list_policies(policies_api, project_id))
  local_policies = read_policies(args.policy_file)
  if args.update:
    existing_policy_map = { policy['name']: policy for policy in existing_policies}

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
    existing_policies = list(list_policies(policies_api, project_id))
  write_policies(args.policy_file, existing_policies)

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
