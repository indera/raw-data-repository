"""The API definition file for the ppi API.

This defines the APIs and the handlers for the APIs.
"""

import api_util
import uuid

import questionnaire
import questionnaire_response
import fhirclient.models.questionnaire
import fhirclient.models.questionnaireresponse

from google.appengine.ext import ndb
from flask import request
from flask.ext.restful import Resource


class QuestionnaireAPI(Resource):
  @api_util.auth_required
  def post(self):
    resource = request.get_json(force=True)
    model = fhirclient.models.questionnaire.Questionnaire(resource)
    if not model.id:
      model.id = str(uuid.uuid4())
    model_json = model.as_json()
    questionnaire.Questionnaire(id=model.id, resource=model_json).put()
    return model_json

  @api_util.auth_required
  def get(self, q_id):
    q = ndb.Key(questionnaire.Questionnaire, q_id).get()
    return q.resource

class QuestionnaireResponseAPI(Resource):
  @api_util.auth_required
  def post(self):
    resource = request.get_json(force=True)
    model = fhirclient.models.questionnaireresponse.QuestionnaireResponse(
        resource)
    if not model.id:
      model.id = str(uuid.uuid4())
    model_json = model.as_json()
    questionnaire_response.QuestionnaireResponse(id=model.id,
                                                 resource=model_json).put()
    return model_json

  @api_util.auth_required
  def get(self, q_id):
    q = ndb.Key(questionnaire_response.QuestionnaireResponse, q_id).get()
    return q.resource