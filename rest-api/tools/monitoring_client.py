import argparse
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

def list_policies(policies_api, project_id):
  name = 'projects/%s' % project_id
  request = policies_api.list(name=name)
  while request:
    response = request.execute()
    for policy in response.get('alertPolicies', []):
      yield policy
    request = policies_api.list_next(request, response)

def main(args):
  project_info = PROJECT_MAP.get(args.project)
  if not project_info:
    print "API key for project %s not found; exiting." % args.project
    sys.exit(-1)

  credentials = GoogleCredentials.get_application_default()
  monitoring = create_monitoring_client(project_info[0], credentials)
  policies_api = monitoring.projects().alertPolicies()
  policies = list_policies(policies_api, project_info[1])
  print "Policies: %s" % list(policies)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--project',
                      help='The project being used',
                      required=True)
  main(parser.parse_args())
