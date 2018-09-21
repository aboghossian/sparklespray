import subprocess
import os
from sparklespray.util import random_string
import re
import sys
from google.cloud import datastore
from google.api_core import exceptions
from google.cloud.storage.client import Client as GSClient
from sparklespray.config import SCOPES
from google.oauth2 import service_account
import google.api_core.exceptions
import time

services_to_add = [  # "storage.googleapis.com",
    "datastore.googleapis.com", "storage-component.googleapis.com", "genomics.googleapis.com", "pubsub.googleapis.com", "storage-api.googleapis.com", "compute.googleapis.com"]

roles_to_add = ["roles/owner", # Eventually drop this
                "roles/compute.admin",
                "roles/datastore.user",
                "roles/genomics.pipelinesRunner",
                "roles/pubsub.editor",
                "roles/storage.admin"]


def _run_cmd(cmd, args):
    cmd = [cmd] + args
    cmd_str = " ".join(cmd)
    print(f"Executing: {cmd_str}")
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print("Command failed. Output:")
        print(e.output)
        sys.exit(1)

def gcloud(args):
    _run_cmd("gcloud", args)
    
def gsutil(args):
    _run_cmd("gsutil", args)

def enable_services(project_id):
    for service in services_to_add:
        gcloud(['services', 'enable',
                service, '--project', project_id])


def create_service_account(service_acct, project_id, key_path):
    gcloud(['iam', 'service-accounts', 'create', service_acct, '--project',
            project_id, '--display-name', "Service account for sparklespray"])

    for role in roles_to_add:
        gcloud(['projects', 'add-iam-policy-binding', project_id, '--member',
                f"serviceAccount:{service_acct}@{project_id}.iam.gserviceaccount.com", "--role", role])

    gcloud(['iam', 'service-accounts', 'keys', 'create', key_path,
            '--iam-account', f"{service_acct}@{project_id}.iam.gserviceaccount.com"])

    # TODO Add check for access google.api_core.exceptions.Forbidden
#    print("Waiting for a minute for permissions to take effect...")
#    time.sleep(60)


def can_reach_datastore_api(project_id, key_path):
    credentials = service_account.Credentials.from_service_account_file(
        key_path, scopes=SCOPES)
    client = datastore.Client(project_id, credentials=credentials)
    try :
        client.get(client.key("invalid", "invalid"))
        return True
    except exceptions.NotFound:
        return False

def setup_project(project_id, key_path, bucket_name):
    print("Enabling services for project {}...".format(project_id))
    enable_services(project_id)
    service_acct = "sparkles-"+random_string(10).lower()
    if not os.path.exists(key_path):
        parent = os.path.dirname(key_path)
        if not os.path.exists(parent):
            os.makedirs(parent)
        print(f"Creating service account and writing key to {key_path} ...")
        create_service_account(service_acct, project_id, key_path)
    else:
        print(
            f"Not creating service account because key already exists at {key_path} Delete this and rerun if you wish to create a new service account.")

    setup_bucket(project_id, key_path, bucket_name)

    if not can_reach_datastore_api(project_id, key_path):
        print("Go to https://console.cloud.google.com/datastore/setup?project={} to choose where to store your data will reside in and then set up will be complete. Select \"Cloud Datastore\" and then select a region close to you, and then \"Create database\".".format(project_id) )
        input("Hit enter once you've completed the above: ")
        print("checking datastore again..")
        if can_reach_datastore_api(project_id, key_path):
            print("Success!")



def setup_bucket(project_id, service_account_key, bucket_name):
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key, scopes=SCOPES)

    client = GSClient(project_id, credentials)
    bucket = client.bucket(bucket_name)
    needs_create = not bucket.exists()

    if needs_create:
        bucket.create()