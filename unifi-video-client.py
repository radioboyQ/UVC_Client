from collections import namedtuple
import json
import logging
from pathlib import Path
from pprint import pprint
import sys
from time import sleep

import click
import pendulum
import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

from UVC_Sync_Lib.UVCSyncLib import UVC_API_ASync

"""
- Log into the DVR and get a list of videos based on search criteria
- Download each video that matches, one at a time
"""
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
# Create base logger
logger = logging.getLogger("UVC-DVR-Downloader")

def datetime_check(ctx, param, value):
    """
    Function to check the datetime input
    """
    if value is None:
        if param.name is 'start_time':
            raise click.BadParameter('You must provide a start time.')
        elif param.name is 'end_time':
            raise click.BadParameter('You must provide an end time.')
        else:
            raise click.BadParameter(f'I\'m being called for {param.name} which is wrong.')
    try:
        # Dummy conversion. Just checking syntax now. Real conversion happens in main.
        denver_dt = pendulum.from_format(value, 'DD-MM-YYYY:HH:mm:ss')
        return value
    except:
        if param.name is 'start_time':
            raise click.BadParameter('Start datetime is not in the correct format.')
        elif param.name is 'end_time':
            raise click.BadParameter('End datetime is not in the correct format.')
        else:
            raise click.BadParameter(f'I\'m being called for {param.name} which is wrong.')

def timezone_check(ctx, param, value):
    """
    Check if the supplied timezone is valid
    """
    if value in pendulum.timezones:
        return value
    else:
        raise click.BadParameter(f'The timezone {value} isn\'t valid, try again.')

@click.command(name='download-videos', context_settings=CONTEXT_SETTINGS)
@click.option('-s', '--start-time', callback=datetime_check, help='Specify a start time in DD-MM-YYYY:HH:mm:ss')
@click.option('-e', '--end-time', callback=datetime_check, help='Specify a start time in DD-MM-YYYY:HH:mm:ss')
@click.option('-u', '--username', help='Unifi Video username', required=True, default='administrator', type=click.STRING)
@click.option('-d', '--hostname', help='Domain name, hostname or IP address for the Video controller. E.g. 127.0.0.1', type=click.STRING, required=True)
@click.option('-p', '--port', help='Port number for the Video controller. Defaults to 7443', default=7443, type=click.IntRange(1, 65535))
@click.option('-o', '--output-dir', help='Directory to save the videos to.', type=click.Path(exists=True, file_okay=False, writable=True, resolve_path=True, allow_dash=True))
@click.option('--password', help='UVC User\'s password. Script will prompt for password later on if not entered. This option exists for scripting.', prompt=True, hide_input=True)
@click.option('-tz', '--timezone', callback=timezone_check, help='Set timezone to be something other than \'America/Denver\'. Default is \'America/Denver\'.', default='America/Denver', type=click.STRING)
@click.argument('camera-names', nargs=-1)
@click.pass_context
def main(ctx, start_time, end_time, username, hostname, port, output_dir, password, camera_names, timezone):
    """Download videos for cameras for a specific time frame.
    
    Times default to America/Denver."""
    console_log_level = 30

    # Base logger
    logger.setLevel(logging.DEBUG)

    # Create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(console_log_level)

    # Create log format
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')

    # Set the format
    ch.setFormatter(formatter)

    # Add console handler to main logger
    logger.addHandler(ch)

    """
    - Log into UVC
    - Get Camera information
    - Search for block of videos
    - Download videos
    """
    
    # Start time conversion
    denver_start = pendulum.from_format(start_time, 'DD-MM-YYYY:HH:mm:ss', tz=timezone)
    utc_start = denver_start.in_tz('UTC')
    # Convert the datetime object to JavaScript Epoch time
    utc_start_epoch = utc_start.int_timestamp * 1000

    # End time conversion
    denver_end = pendulum.from_format(end_time, 'DD-MM-YYYY:HH:mm:ss', tz=timezone)
    utc_end = denver_end.in_tz('UTC')
    # Convert the datetime object to JavaScript Epoch time
    utc_end_epoch = utc_end.int_timestamp * 1000

    client = UVC_API_ASync(hostname, port, username, password, logger, sleep_time=0) # , proxy=proxy)

    raw_resp = client.login()

    raw_resp = client.camera_info()

    camera_id_list = client.camera_name(camera_names)

    client.clip_search(epoch_start=utc_start_epoch, epoch_end=utc_end_epoch, camera_id_list=camera_id_list)

    client.download_footage(Path(output_dir))

    sleep(.2)

    raw_resp = client.logout()



if __name__ == "__main__":
    main()