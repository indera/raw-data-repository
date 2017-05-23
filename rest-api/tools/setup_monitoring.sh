#!/bin/bash

# Sets up or retrieves monitoring info for Stackdriver in a given environment.

# Example usage:
# tools/setup_monitoring.sh --account dan.rodney@pmi-ops.org --project all-of-us-rdr-staging [--update]

EXTRA_ARGS=
USAGE="tools/setup_monitoring.sh --account <ACCOUNT> --project <PROJECT> [--update]"
while true; do
  case "$1" in
    --account) ACCOUNT=$2; shift 2;;
    --project) PROJECT=$2; shift 2;;
    --update) EXTRA_ARGS="--update"; shift 1;;
    -- ) shift; break ;;
    * ) break ;;
  esac
done

if [ -z "${PROJECT}" ]
then
  echo "--project is required. $USAGE"
  exit 1
fi

TEMPLATES_FILE=config/alerts/alert_templates.json

if [ -z "${ACCOUNT}" ]
then
  echo "--account is required. $USAGE"
  exit 1
fi

if [ -z "${CREDS_ACCOUNT}" ]
then
  CREDS_ACCOUNT="${ACCOUNT}"
fi

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
export PYTHONPATH=$PYTHONPATH:${BASE_DIR}:${BASE_DIR}/lib

source tools/auth_setup.sh

(export GOOGLE_APPLICATION_CREDENTIALS="${CREDS_FILE}"; cd ${BASE_DIR};
 python tools/monitoring_client.py --project $PROJECT --templates_file $TEMPLATES_FILE $EXTRA_ARGS)
