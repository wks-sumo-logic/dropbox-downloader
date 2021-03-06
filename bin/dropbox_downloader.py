#!/usr/bin/env python3

"""
dropbox_downloader - Simple script to retrieve Dropbox data

script flow:
    + evaluate/validate variables
    + create directory and files if needed
    + gets timestamps
    + sets timestamps
    + gets data and sanitizes it
    + retrieves any extra based on cursors
    + persists the data locally
"""

import os
import sys
import json
import datetime
import logging
import argparse
import configparser
import requests

logging.basicConfig(level=logging.INFO)

PARSER = argparse.ArgumentParser(description="""
Collect data from dropbox via API and cache data locally
""")

PARSER.add_argument("-t", metavar='<token>', dest='MY_BEARER_TOKEN', \
                    help="set token")

PARSER.add_argument("-r", metavar='<start>', dest='MY_TIME_RANGE', \
                    type=int,default=0, help="set start time")

PARSER.add_argument("-d", metavar='<cachedir>', dest='MY_CACHE_DIR', \
                    help="set directory")

PARSER.add_argument("-c", metavar='<cfgfile>', dest='MY_CFG_FILE', \
                    help="use config file")

PARSER.add_argument("-v", type=int, default=0, metavar='<verbose>', \
                    dest='VERBOSE', help="increase verbosity")

ARGS = PARSER.parse_args()

TIME_RANGE = 0
DROPBOX_BASE_DIR = '/var/tmp/dropbox'
BEARER_TOKEN = 'UNSET'

if ARGS.MY_CFG_FILE:

    CFGFILE = os.path.abspath(ARGS.MY_CFG_FILE)
    CONFIG = configparser.ConfigParser()
    CONFIG.read(CFGFILE)

    if CONFIG.has_option('Default', 'BEARER_TOKEN'):
        BEARER_TOKEN = json.loads(CONFIG.get("Default", "BEARER_TOKEN"))

    if CONFIG.has_option('Default', 'CACHE_DIR'):
        DROPBOX_BASE_DIR = os.path.abspath(json.loads(CONFIG.get("Default", "CACHE_DIR")))

    if CONFIG.has_option('Default', 'TIME_RANGE'):
        TIME_RANGE = json.loads(CONFIG.get("Default", "TIME_RANGE"))

if ARGS.MY_BEARER_TOKEN:
    BEARER_TOKEN = ARGS.MY_BEARER_TOKEN

if ARGS.MY_CACHE_DIR:
    DROPBOX_BASE_DIR = os.path.abspath(ARGS.MY_CACHE_DIR)

if ARGS.MY_TIME_RANGE:
    TIME_RANGE = ARGS.MY_TIME_RANGE

if BEARER_TOKEN == "UNSET":
    logging.error('BEARER TOKEN unset. Exiting.')
    sys.exit(10)

if ARGS.VERBOSE > 5:
    print('Token: {}'.format(BEARER_TOKEN))
    print('Cache: {}'.format(DROPBOX_BASE_DIR))
    print('Range: {}'.format(TIME_RANGE))

DROPBOX_LOCK_DIR = os.path.join(DROPBOX_BASE_DIR, 'lock')
DROPBOX_LOCK_FILE = os.path.join(DROPBOX_LOCK_DIR, 'dropbox-timestamp.lock')
if ARGS.VERBOSE > 3:
    logging.info('resolving lock_directory: %s', DROPBOX_LOCK_FILE)

DROPBOX_LOGS_DIR = os.path.join(DROPBOX_BASE_DIR, 'logs')
DROPBOX_LOGS_FILE = os.path.join(DROPBOX_LOGS_DIR, 'dropbox-timestamp.log')
if ARGS.VERBOSE > 3:
    logging.info('resolving logs_directory: %s', DROPBOX_LOGS_FILE)

TODAY = datetime.datetime.today()

TIMESTAMP = "{:04d}-{:02d}-{:02d}T00:00:00.000".format(TODAY.year, TODAY.month, TODAY.day)

DROPBOX_BASE_URL = 'https://api.dropboxapi.com/2/team_log/get_events'

def get_timestamp_data():

    """
    Collect the timestamp from either a local file or current date: DROPBOX_LOCK_FILE
    """

    for target_dir in ( DROPBOX_LOCK_DIR, DROPBOX_LOGS_DIR ):
        if not os.path.exists(target_dir):
            if ARGS.VERBOSE > 5:
                logging.info('creating_directory: %s', target_dir)
            os.makedirs(target_dir)

    my_timestamp = TIMESTAMP

    if os.path.exists(DROPBOX_LOCK_FILE):
        if ARGS.VERBOSE > 5:
            logging.info('reading_timestamp: %s', DROPBOX_LOCK_FILE)
        with open(DROPBOX_LOCK_FILE, 'r') as time_stamp_file:
            my_timestamp = time_stamp_file.read()

    my_timestamp = my_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    return my_timestamp, DROPBOX_LOCK_FILE

def put_timestamp_data(my_tsvalue, my_tsfile):

    """
    Persist the timestamp into a local file for comparison: DROPBOX_LOCK_FILE
    """

    my_timestamp = my_tsvalue.replace(microsecond=0).isoformat()
    try:
        with open(my_tsfile, 'w') as time_stamp_file:
            if ARGS.VERBOSE > 5:
                logging.info('writing_timestamp: %s', DROPBOX_LOCK_FILE)
            time_stamp_file.write(my_timestamp)
    except OSError as my_error:
        logging.error('Unexpected issue encountered (%d): %s', my_error.errno, my_error.strerror)
        raise

    my_timestamp = my_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    return my_timestamp

def remove_dot_key(json_object):

    """
    Clean up Json object: json_object
    """

    for key in json_object.keys():
        new_key = json_object.replace(".","")
        if new_key != key:
            json_object[new_key] = json_object[key]
            del json_object[key]
    return json_object

if __name__ == '__main__':

    MY_STAMP, LOCK_FILE = get_timestamp_data()

    start_date = TODAY - datetime.timedelta(days=int(TIME_RANGE))

    MY_STAMP = "{:04d}-{:02d}-{:02d}T00:00:00Z".format(
                 start_date.year, start_date.month, start_date.day)

    now = put_timestamp_data(datetime.datetime.now(), LOCK_FILE)

    start_end_time = { 'start_time': MY_STAMP, 'end_time': now }
    json_data= { 'time': start_end_time }

    DROPBOX_TARGET_URL = DROPBOX_BASE_URL

    TOTAL_EVENTS = 0

    CONTINUE_FLAG = "no"

    GET_DATA = "true"

    while GET_DATA == "true":

        header_dict = {}

        header_dict['Accept'] = 'application/json'
        header_dict['Content-Type'] = 'application/json'
        header_dict['Authorization'] = 'Bearer ' + BEARER_TOKEN

        get_response = requests.post(DROPBOX_TARGET_URL,
                                     data=json.dumps(json_data),headers=header_dict)

        my_status = get_response.status_code
        my_payload = get_response.content

        if get_response.status_code != 200:
            logging.error('status_code: %d - %s', my_status, my_payload)
            sys.exit(get_response.status_code)
        else:
            ### dropbox_json_logs = json.loads(get_response.content, object_hook=remove_dot_key)
            dropbox_json_logs = json.loads(get_response.content)
        events = dropbox_json_logs['events']

        events_size = len(events)
        TOTAL_EVENTS += events_size

        output_file = open(DROPBOX_LOGS_FILE, 'a+')
        for event in events:
            json_log = json.dumps(event)
            output_file.write('{}\n'.format(json_log))

        if dropbox_json_logs['has_more'] == 'true':
            DROPBOX_TARGET_URL = 'https://api.dropboxapi.com/2/team_log/get_events/continue'
            json_data = { 'cursor': dropbox_json_logs['cursor'] }
            if ARGS.VERBOSE > 7:
                logging.info('Retrieved: %d bytes and getting more data.', events_size)
        else:
            GET_DATA = "false"
