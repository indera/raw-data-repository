import argparse
import json
import logging
import os
import sys
from oauth2client.client import GoogleCredentials
from googleapiclient.discovery import build

_USER_METRIC_FILTER = 'metric.type = starts_with("logging.googleapis.com/user/")'
_POLICIES_KEY = 'policies'
_METRIC_DESCRIPTORS_KEY = 'metricDescriptors'
_PROJECT_INFO_FILE = 'config/alerts/project_info.json'

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

def read_templates(templates_file):
  if os.path.exists(templates_file):
    with open(templates_file, 'r') as fp:
      templates_json = json.load(fp)
      return templates_json
  else:
    return {}

def policy_to_template(policy, project_name):
  template = dict(policy)
  for f in ['name', 'mutationRecord', 'creationRecord', 'notificationChannels']:
    if template.get(f):
      del template[f]
  for i in range(0, len(template['conditions'])):
    condition = template['conditions'][i]
    if not condition.get('conditionThreshold'):
      return None
    else:
      del condition['name']
      condition['displayName'] = condition['displayName'].replace(project_name, "${PROJECT_NAME}")
      threshold = condition['conditionThreshold']
      if threshold.get('filter'):
        threshold['filter'] = threshold['filter'].replace(project_name, "${PROJECT_NAME}")
    return template

def template_to_policy(template, project_name, project_info, name=None):
  policy = dict(template)
  notification_channels = []
  for notification_channel_id in project_info['notification_channel_ids']:
    notification_channels.append('projects/%s/notificationChannels/%s' % (project_name,
                                                                          notification_channel_id))
  policy['notificationChannels'] = notification_channels
  for condition in policy['conditions']:
    condition['displayName'] = condition['displayName'].replace("${PROJECT_NAME}", project_name)
    threshold = condition['conditionThreshold']
    if threshold.get('filter'):
      threshold['filter'] = threshold['filter'].replace("${PROJECT_NAME}", project_name)
  if name:
    policy['name'] = name
  return policy

def metric_descriptor_to_template(metric_descriptor):
  template = dict(metric_descriptor)
  del template['name']
  return template

def template_to_metric_descriptor(template, project_name):
  metric_descriptor = dict(template)
  metric_descriptor['name'] = 'projects/%s/metricDescriptors/%s' % (project_name, template['type'])
  return metric_descriptor

def write_templates(templates_file, policies, metric_descriptors, project_name):
  policy_templates = []
  for policy in policies:
    policy_template = policy_to_template(policy, project_name)
    if policy_template:
      policy_templates.append(policy_template)

  metric_descriptor_templates = []
  for metric_descriptor in metric_descriptors:
    metric_descriptor_templates.append(metric_descriptor_to_template(metric_descriptor))

  with open(templates_file, 'w') as fp:
    templates_json = {_POLICIES_KEY: policy_templates,
                      _METRIC_DESCRIPTORS_KEY: metric_descriptor_templates}
    json.dump(templates_json, fp, indent=4)
  logging.info('Wrote %d policies and %d metric descriptors to %s.' %
               (len(policy_templates), len(metric_descriptor_templates), templates_file))

def create_metric_descriptor(metric_descriptors_api, project_id, metric_descriptor):
  print "name = %s, body = %s" % (make_name(project_id), metric_descriptor)
  result = metric_descriptors_api.create(name=make_name(project_id),
                                         body=metric_descriptor).execute()
  logging.info('Created metric_descriptor: %s' % result)

def update_from_templates(existing_policies, existing_metric_descriptors, templates_json,
                          project_name, project_info, metric_descriptors_api, policies_api):
  project_id = project_info['project_id']
  existing_policy_map = {policy['displayName']: policy for policy in existing_policies}
  existing_descriptor_map = {descriptor['type']: descriptor
                             for descriptor in existing_metric_descriptors}
  policy_templates = templates_json.get(_POLICIES_KEY) or []
  metric_descriptor_templates = templates_json.get(_METRIC_DESCRIPTORS_KEY) or []

  # Update metric descriptors.
  for metric_descriptor_template in metric_descriptor_templates:
    descriptor_type = metric_descriptor_template.get('type')
    existing_descriptor = existing_descriptor_map.get(descriptor_type)
    if not existing_descriptor:
      logging.info('Descriptor with type %s does not exist, creating.', descriptor_type)
      new_descriptor = template_to_metric_descriptor(metric_descriptor_template, project_name)
      create_metric_descriptor(metric_descriptors_api, project_id, new_descriptor)
    else:
      if metric_descriptor_to_template(existing_descriptor) == metric_descriptor_template:
        logging.info('Descriptor of type %s remains unchanged.', descriptor_type)
      else:
        logging.warning('Descriptor of type %s differs in content (%s vs %s); ' +
                        'rename to make new descriptor.',
                        descriptor_type, metric_descriptor_template,
                        metric_descriptor_to_template(existing_descriptor))

  # Then update policies.
  for policy_template in policy_templates:
    policy_name = policy_template['displayName']
    existing_policy = existing_policy_map.get(policy_name)
    if not existing_policy:
      logging.info('Policy %s does not exist, creating with new name.', policy_name)
      new_policy = template_to_policy(policy_template, project_name, project_info)
      create_policy(policies_api, project_id, new_policy)
    else:
      if policy_to_template(existing_policy, project_name) == policy_template:
        logging.info('Policy %s remains unchanged.', policy_name)
      else:
        logging.info('Updating policy %s.', existing_policy['name'])
        updated_policy = template_to_policy(policy_template, project_name,
                                            project_info, existing_policy['name'])
        update_policy(policies_api, project_id, updated_policy)


def main(args):
  logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(levelname)s: %(message)s')
  with open(_PROJECT_INFO_FILE) as project_info_file:
    project_info_map = json.load(project_info_file)

  project_info = project_info_map.get(args.project)
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
  if args.update:
    templates_json = read_templates(args.templates_file)
    update_from_templates(existing_policies, existing_metric_descriptors, templates_json,
                          args.project, project_info, metric_descriptors_api, policies_api)
  else:
    write_templates(args.templates_file, existing_policies, existing_metric_descriptors,
                    args.project)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--project',
                      help='The project being used',
                      required=True)
  parser.add_argument('--templates_file',
                      help='A file containing alert policy templates to import and/or export to',
                      required=True)
  parser.add_argument('--update',
                      help='Specify this if you want to import policies into Stackdriver; ' +
                      'do not specify it if you want to export policies',
                      action='store_true')
  main(parser.parse_args())
