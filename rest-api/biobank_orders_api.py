"""The API definition file for the Biobank orders API.

This defines the APIs and the handlers for the APIs.
"""

import datetime
import uuid

import api_util
import base_api
import biobank_order
import participant

from protorpc import message_types
from protorpc import messages

from google.appengine.ext import ndb
from flask import Flask, request
from flask.ext.restful import Resource, reqparse, abort
from werkzeug.exceptions import BadRequest, NotFound

class BiobankOrderAPI(base_api.BaseApi):
  valid_tests = frozenset(['1ED10', '2ED10', '1ED04', '1SST8', '1PST8', '1HEP4',
                           '1UR10', '1SAL'])
  
  def __init__(self):
    super(BiobankOrderAPI, self).__init__(biobank_order.DAO)

  def validate_object(self, order, a_id=None):
     if not order.subject:
       raise BadRequest('Missing field: subject')
     if not order.created:
       raise BadRequest('Missing field: created')     
     if not a_id:
       raise BadRequest('Missing participant ID')
     if order.subject != 'Patient/{}'.format(a_id):
       raise BadRequest('Subject {} invalid.'.format(order.subject))     
     for sample in order.samples:
       if not sample.test:
         raise BadRequest('Missing field: sample.test in sample {}'
                          .format(sample))
       if not sample.description:
         raise BadRequest('Missing field: sample.description in sample {}' 
                          .format(sample))
       if not sample.test in BiobankOrderAPI.valid_tests:
         raise BadRequest('Invalid test value: {}'.format(sample.test))  
     # Verify that all order identifiers are not in use by another order
     if not order.identifier or len(order.identifier) < 1:
       raise BadRequest('At least one identifier is required')
     for identifier in order.identifier:
       other_order = biobank_order.DAO.find_by_identifier(identifier)
       if other_order and other_order.id != order.id:
         raise BadRequest('Identifier {} is already in use by another order'.format(identifier))       
     # This will raise if the participant can't be found.  Loading for validation
     # only.
     participant.DAO.load(a_id)   
   