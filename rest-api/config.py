"""Configuration parameters.

Contains things such as the accounts allowed access to the system.
"""
import cachetools
import logging
import time

import data_access_object

from google.appengine.ext import ndb

from werkzeug.exceptions import NotFound

# Key that the main server configuration is stored under
CONFIG_SINGLETON_KEY = 'current_config'
# Key that the database configuration is stored under
DB_CONFIG_KEY = 'db_config'

CONFIG_CACHE_TTL_SECONDS = 60

BIOBANK_ID_PREFIX = 'biobank_id_prefix'
METRICS_SHARDS = 'metrics_shards'
PARTICIPANT_SUMMARY_SHARDS = 'participant_summary_shards'
AGE_RANGE_SHARDS = 'age_range_shards'
BIOBANK_SAMPLES_SHARDS = 'biobank_samples_shards'
BIOBANK_SAMPLES_BUCKET_NAME = 'biobank_samples_bucket_name'
CONSENT_PDF_BUCKET = 'consent_pdf_bucket'
USER_INFO = 'user_info'
SYNC_SHARDS_PER_CHANNEL = 'sync_shards_per_channel'
MEASUREMENTS_ENTITIES_PER_SYNC = 'measurements_entities_per_sync'
BASELINE_PPI_QUESTIONNAIRE_FIELDS = 'baseline_ppi_questionnaire_fields'
PPI_QUESTIONNAIRE_FIELDS = 'ppi_questionnaire_fields'
BASELINE_SAMPLE_TEST_CODES = 'baseline_sample_test_codes'
DNA_SAMPLE_TEST_CODES = 'dna_sample_test_codes'
NATIVE_AMERICAN_RACE_CODES = 'native_american_race_codes'
# Allow requests which are never permitted in production. These include fake
# timestamps for reuqests, unauthenticated requests to create fake data, etc.
ALLOW_NONPROD_REQUESTS = 'allow_nonprod_requests'

# Settings for e-mail alerts for failed jobs.
INTERNAL_STATUS_MAIL_SENDER = 'internal_status_email_sender'
INTERNAL_STATUS_MAIL_RECIPIENTS = 'internal_status_email_recipients'
BIOBANK_STATUS_MAIL_RECIPIENTS = 'biobank_status_mail_recipients'

# True if we should add codes referenced in questionnaires that
# aren't in the code book; false if we should reject the questionnaires.
ADD_QUESTIONNAIRE_CODES_IF_MISSING = 'add_questionnaire_codes_if_missing'

REQUIRED_CONFIG_KEYS = [BIOBANK_SAMPLES_BUCKET_NAME]

def _get_config(key):
  """This function is called by the `TTLCache` to grab an updated config.
  Note that `TTLCache` always supplies a key, which we assert here."""
  assert key in (CONFIG_SINGLETON_KEY, DB_CONFIG_KEY)
  config_entity = DAO().load_if_present(key)
  if config_entity is None:
    raise KeyError('No config for %r.' % key)
  return config_entity.configuration

def override_setting(key, value):
  """Overrides a config setting. Used in tests."""
  CONFIG_OVERRIDES[key] = value

CONFIG_CACHE = cachetools.TTLCache(1, ttl=CONFIG_CACHE_TTL_SECONDS, missing=_get_config)
CONFIG_OVERRIDES = {}

# Used to override the whole config in tests without use of the REST API
def store_current_config(config_json):
  conf_ndb_key = ndb.Key(Configuration, CONFIG_SINGLETON_KEY)
  conf = Configuration(key=conf_ndb_key, configuration=config_json)
  DAO().store(conf)

class MissingConfigException(BaseException):
  """Exception raised if the setting does not exist"""


class InvalidConfigException(BaseException):
  """Exception raised when the config setting is a not in the expected form."""


class Configuration(ndb.Model):
  configuration = ndb.JsonProperty()


class ConfigurationDAO(data_access_object.DataAccessObject):
  def __init__(self):
    super(ConfigurationDAO, self).__init__(Configuration)

  def properties_from_json(self, dict_, ancestor_id, id_):
    return {
        "configuration": dict_
    }

  def properties_to_json(self, dict_):
    return dict_.get('configuration', {})

  def load_if_present(self, id_, ancestor_id=None):
    obj = super(ConfigurationDAO, self).load_if_present(id_, ancestor_id)
    if not obj and id_ == CONFIG_SINGLETON_KEY:
      initialize_config()
      obj = super(ConfigurationDAO, self).load_if_present(id_, ancestor_id)
    return obj

  def store(self, model, date=None, client_id=None):
    ret = super(ConfigurationDAO, self).store(model, date, client_id)
    invalidate()
    return ret

def DAO():
  return ConfigurationDAO()

_NO_DEFAULT = '_NO_DEFAULT'

def getSettingJson(key, default=_NO_DEFAULT):
  """Gets a config setting as an arbitrary JSON structure

  Args:
    key: The config key to retrieve entries for.
    default: What to return if the key does not exist in the datastore.

  Returns:
    The value from the Config store, or the default if not present

  Raises:
    MissingConfigException: If the config key does not exist in the datastore,
      and a default is not provided.
  """
  config_values = CONFIG_OVERRIDES.get(key)
  if config_values is not None:
    return config_values

  current_config = CONFIG_CACHE[CONFIG_SINGLETON_KEY]
  config_values = current_config.get(key, default)
  if config_values == _NO_DEFAULT:
    raise MissingConfigException('Config key "{}" has no values.'.format(key))

  return config_values


def getSettingList(key, default=_NO_DEFAULT):
  """Gets all config settings for a given key.

  Args:
    key: The config key to retrieve entries for.
    default: What to return if the key does not exist in the datastore.

  Returns:
    A list of all config entries matching this key.

  Raises:
    MissingConfigException: If the config key does not exist in the datastore,
      and a default is not provided.
  """
  config_json = getSettingJson(key, default)
  if isinstance(config_json, list):
    return config_json

  raise InvalidConfigException(
      'Config key {} is a {} instead of a list'.format(key, type(config_json)))


def getSetting(key, default=_NO_DEFAULT):
  """Gets a config where there is only a single setting for a given key.

  Args:
    key: The config key to look up.
    default: If the config key is not found in the datastore, this will be
      returned.

  Raises:
    InvalidConfigException: If the key has multiple entries in the datastore.
    MissingConfigException: If the config key does not exist in the datastore,
     and a default is not provided.
  """
  if default != _NO_DEFAULT:
    default = [default]
  settings_list = getSettingList(key, default)

  if len(settings_list) != 1:
    raise InvalidConfigException(
        'Config key {} has multiple entries in datastore.'.format(key))
  return settings_list[0]

def initialize_config():
  """Initalize an empty configuration."""
  conf_ndb_key = ndb.Key(Configuration, CONFIG_SINGLETON_KEY)
  Configuration(key=conf_ndb_key, configuration={}).put()
  logging.info('Setting an empty configuration.')

def invalidate():
  """Invalidate the config cache when we learn something new has been written.
  The `expire` function takes one argument, which effectively says, "pretend
  it's this time, and expire everything that's due to expire by then"."""
  CONFIG_CACHE.expire(time.time() + CONFIG_CACHE_TTL_SECONDS)


def insert_config(key, value_list):
  """Updates a config key.  Used for tests"""
  conf = DAO().load(CONFIG_SINGLETON_KEY)
  conf.configuration[key] = value_list
  DAO().store(conf)
  invalidate()

def get_config_that_was_active_at(key, date):
  history_model = DAO().history_model
  q = history_model.query(ancestor=ndb.Key('Configuration', key));
  q = q.filter(history_model.date < date).order(-DAO().history_model.date)
  h = q.fetch(limit=1)
  if not h:
    raise NotFound('No history object active at {}.'.format(date))
  return h[0].obj

def get_db_config():
  return CONFIG_CACHE[DB_CONFIG_KEY]
