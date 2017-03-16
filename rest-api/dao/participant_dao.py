import clock
import json
from dao.base_dao import BaseDao, UpdatableDao
from dao.hpo_dao import HPODao
from model.participant_summary import ParticipantSummary
from model.participant import Participant, ParticipantHistory
from participant_enums import UNSET_HPO_ID
from werkzeug.exceptions import BadRequest

class ParticipantHistoryDao(BaseDao):
  """Maintains version history for participants.

  All previous versions of a participant are maintained (with the same participantId value and
  a new version value for each update.)

  Old versions of a participant are used to generate historical metrics (e.g. count the number of
  participants with different statuses or HPO IDs over time).

  Do not use this DAO for write operations directly; instead use ParticipantDao.
  """
  def __init__(self):
    super(ParticipantHistoryDao, self).__init__(ParticipantHistory)

  def get_id(self, obj):
    return [obj.participantId, obj.version]



class ParticipantDao(UpdatableDao):
  def __init__(self):
    super(ParticipantDao, self).__init__(Participant)

  def get_id(self, obj):
    return obj.participantId

  def insert_with_session(self, session, obj):
    obj.hpoId = self.get_hpo_id(obj)
    obj.version = 1
    obj.signUpTime = clock.CLOCK.now()
    obj.lastModified = obj.signUpTime
    super(ParticipantDao, self).insert_with_session(session, obj)
    obj.participantSummary = ParticipantSummary(participantId=obj.participantId,
                                                biobankId=obj.biobankId,
                                                signUpTime=obj.signUpTime,
                                                hpoId=obj.hpoId)
    history = ParticipantHistory()
    history.fromdict(obj.asdict(), allow_pk=True)
    session.add(history)
    return obj

  def insert(self, obj):
    if obj.participantId:
      assert obj.biobankId
      return super(ParticipantDao, self).insert(obj)
    assert not obj.biobankId
    return self._insert_with_random_id(obj, ('participantId', 'biobankId'))

  def _update_history(self, session, obj, existing_obj):
    # Increment the version and add a new history entry.
    obj.version = existing_obj.version + 1
    history = ParticipantHistory()
    history.fromdict(obj.asdict(), allow_pk=True)
    session.add(history)

  def _do_update(self, session, obj, existing_obj):
    # If the provider link changes, update the HPO ID on the participant and its summary.
    obj.lastModified = clock.CLOCK.now()
    obj.signUpTime = existing_obj.signUpTime
    obj.biobankId = existing_obj.biobankId
    obj.hpoId = existing_obj.hpoId
    if obj.providerLink != existing_obj.providerLink:
      new_hpo_id = self.get_hpo_id(obj)
      if new_hpo_id != existing_obj.hpoId:
        obj.hpoId = new_hpo_id
        obj.participantSummary = ParticipantSummary()
        obj.participantSummary.fromdict(existing_obj.participantSummary.asdict(), allow_pk=True)
        obj.participantSummary.hpoId = new_hpo_id
    self._update_history(session, obj, existing_obj)
    super(ParticipantDao, self)._do_update(session, obj, existing_obj)

  def get_hpo_id(self, obj):
    hpo_name = get_HPO_name_from_participant(obj)
    if hpo_name:
      hpo = HPODao().get_by_name(hpo_name)
      if not hpo:
        raise BadRequest('No HPO found with name %s' % hpo_name)
      return hpo.hpoId
    else:
      return UNSET_HPO_ID

  def validate_participant_reference(self, session, obj):
    """Raises BadRequest if an object has a missing or invalid participantId reference."""
    if obj.participantId is None:
      raise BadRequest('%s.participantId required.' % obj.__class__.__name__)
    if self.get_with_session(session, obj.participantId) is None:
      raise BadRequest(
          '%s.participantId %r is not found.' % (obj.__class__.__name__, obj.participantId))

  def get_valid_biobank_id_set(self, session):
    return set([row[0] for row in session.query(Participant.biobankId)])


# TODO(danrodney): remove this logic from old participant code when done
def get_primary_provider_link(participant):
  if participant.providerLink:
    provider_links = json.loads(participant.providerLink)
    if provider_links:
      for provider in provider_links:
        if provider.get('primary') == True:
          return provider
  return None

def get_HPO_name_from_participant(participant):
  """Returns ExtractionResult with the string representing the HPO."""
  primary_provider_link = get_primary_provider_link(participant)
  if primary_provider_link and primary_provider_link.get('organization'):
    reference = primary_provider_link.get('organization').get('reference')
    if reference and reference.lower().startswith('organization/'):
      return reference[13:]
  return None

