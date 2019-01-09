from collections import namedtuple
import json
import logging
from pathlib import Path
from pprint import pprint
import sys
from time import sleep, strftime, gmtime

import click
import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


class UVC_API_ASync(object):
    """
    Class of functions for talking to the UVC device
    """

    def __init__(self, uvc_server, uvc_https_port, usrname, passwd, logger, ssl_verify=False, proxy=None, sleep_time=0.2, chunk_size=1024):
        self.uvc_server = uvc_server
        self.uvc_https_port = uvc_https_port
        self.usrname = usrname
        self.passwd = passwd
        self.logger = logger
        self.ssl_verify = ssl_verify
        self.url = f"https://{uvc_server}:{uvc_https_port}"
        self.auth_cookie_name = 'JSESSIONID_AV'
        self.auth_cookie_value = None
        self.camera_mgrd_filter_name = 'cameras.isManagedFilterOn'
        self.camera_mgrd_filter_value = False
        self.session = requests.Session()
        self.apiKey = None
        self.camera_info_dict = dict()
        self.dict_info_clip = dict()
        self.sleep_time = sleep_time
        self.chunk_size = chunk_size

        # Build the session
        self.session.verify = self.ssl_verify
        self.session.headers = {'User-Agent': 'UVCSyncLib'}
        if proxy is None:
            # Don't set proxy config
            self.logger.debug('Not using a proxy')
        else:
            # Set proxy param
            self.logger.debug(f'Using proxy {proxy}')
            self.session.proxies = proxy

    def login(self):
        # Logs into UVC host
        login_payload = {'username': self.usrname, 'password': self.passwd}

        r = self.session.post(f"{self.url}/api/2.0/login", json=login_payload)

        # r = self.session.post(f"{self.url}/api/2.0/login", json=login_payload, verify=self.ssl_verify)
        if r.status_code is not 200:
            self.logger.critical(f"Failed to log into the DVR. Check the error {r.json()}")
            sys.exit(1)

        elif r.status_code is 200:
            self.logger.debug("Successfully logged into the DVR")

            # Request all the user's data
            user_resp = self.session.get(f"{self.url}/api/2.0/user")
            user_data = user_resp.json()
            self.logger.debug("Obtained all user config data")
            # Get API token for the user
            for d in user_data['data']:
                if d['account']['username'] == self.usrname:
                    self.apiKey = d['apiKey']
                    self.logger.debug(f"Obtained {self.usrname}'s API key successfully")
            return r

    def logout(self):
        # Logs out of UVC host

        r = self.session.get(f"{self.url}/api/2.0/logout")
        if r.status_code is not 200:
            self.logger.critical(f"Failed to log out of the DVR. Check the error {r.text}")
            sys.exit(1)

        elif r.status_code is 200:
            self.logger.debug("Successfully logged out the DVR")

            return r

    def camera_info(self):
        """
        Obtain information about the cameras. This is the bootstrap page
        """
        camera_info = namedtuple('CameraInformation',
                                 ['camera_id', 'camera_name', 'camera_addr', 'last_rec_id', 'last_rec_start_time_epoch',
                                  'rtsp_uri', 'rtsp_enabled'])

        r = self.session.get(f"{self.url}/api/2.0/bootstrap", cookies=self.session.cookies.update({'cameras.isManagedFilterOn': 'false'}))
        if r.status_code is not 200:
            self.logger.critical(f'Failed to obtain the camera data. Check the error {r.text}')
            sys.exit(1)
        elif r.status_code is 200:
            self.logger.debug("Obtained the bootstrap page.")

        bootstrap_data = r.json()

        # Check if anyting weird is going on with the bootstrap data
        try:
            bootstrap_data['data'][0]['cameras']
        except KeyError:
            self.logger.error('The UVC didn\'t provide the bootstrap data for the cameras.')
            pprint(bootstrap_data['data'])
            sys.exit(1)
        else:
            # Check if we got all of the data from bootstrap
            if len(bootstrap_data['data'][0]['cameras']) > 0:
                self.logger.debug('Obtained camera data from bootstrap endpoint')
            else:
                self.logger.critical('The bootstrap endpoint didn\'t provide the correct data. Exiting.')
                sys.exit(1)

            for c in bootstrap_data['data'][0]['cameras']:
                camera_id = c['_id']
                camera_name = c['deviceSettings']['name']
                camera_addr = c['host']
                last_rec_id = c['lastRecordingId']
                last_rec_start_time_epoch = c['lastRecordingStartTime']
                for bitrate in c['channels']:
                    if bitrate['id'] == '1':
                        rtsp_uri = bitrate['rtspUris'][1]
                        rtsp_enabled = bitrate['isRtspEnabled']
                self.camera_info_dict.update({camera_id: camera_info(camera_id, camera_name, camera_addr, last_rec_id, last_rec_start_time_epoch, rtsp_uri, rtsp_enabled)})

    def camera_name(self, camera_name_list):
        """
        Function to parse out the camera's name from a given input
        """
        camera_id_list = list()
        for id in self.camera_info_dict:
            if self.camera_info_dict[id].camera_name in camera_name_list:
                # print(self.camera_info_dict[id].camera_id)
                camera_id_list.append(self.camera_info_dict[id].camera_id)
        return camera_id_list


    def clip_meta_data(self, clip_id_list):
        """
        Get the meta data for each clip ID
        - Check if
        """
        meta_cookies = {'lastMap': 'null', 'lastLiveView': 'null'}
        meta_cookies.update(self.session.cookies)
        camera_meta_data_list = list()
        clip_id_list_len = len(clip_id_list)
        # url_id_params = str()
        clip_info = namedtuple('ClipInformation',
                                     ['clip_id', 'startTime', 'endTime', 'eventType', 'inProgress', 'locked',
                                      'cameraName', 'recordingPathId', 'fullFileName'])

        # Loop over the list and request data for each clip
        with click.progressbar(clip_id_list, length=clip_id_list_len, label='Clip Data Downloaded', show_eta=False, show_percent=False, show_pos=True) as bar:
            for id in bar:
                # Prepare the search data
                req = requests.Request('GET', f"{self.url}/api/2.0/recording/{id}", cookies=meta_cookies)
                prepped = req.prepare()

                r = self.session.send(prepped)
                if r.status_code is 200:
                    # We grabbed clip meta data, continue.
                    # self.logger.debug(f'Meta data obtained for clip {id}.')
                    camera_meta_data_list.append(r.json())
                    sleep(self.sleep_time)
                elif r.status_code is 401:
                    self.logger.critical(f'Unauthorized, exiting.')
                    sys.exit(1)
                else:
                    self.logger.critical(f'Unexpected error occured: {r.status_code}. Exiting.')
                    sys.exit(1)

        for c in camera_meta_data_list:
            # Skip clips that are in progress of recording
            c = c['data'][0]
            if c['inProgress']:
                self.logger.warning(f"Skipping clip ID {c['_id']}, it\'s still recording")
            else:
                # Clips that are done recording
                clip_id = c['_id']
                startTime = c['startTime']
                endTime = c['endTime']
                eventType = c['eventType']
                inProgress = c['inProgress']
                locked = c['locked']
                cameraName = c['meta']['cameraName']
                recordingPathId = c['meta']['recordingPathId']
                mod_cam_name = cameraName.replace(' ', '_').lower()
                human_start_time = strftime('%d_%m_%Y-%H:%M:%S',  gmtime(startTime/1000.))
                fullFileName = f"{human_start_time}-{mod_cam_name}.mp4"

                self.dict_info_clip.update({clip_id: clip_info(clip_id, startTime, endTime, eventType, inProgress, locked, cameraName, recordingPathId, fullFileName)})

    def clip_search(self, epoch_start, epoch_end, camera_id_list= list()):
        """
        Search for clips
        """
        sortBy = 'startTime'
        idsOnly = True
        sort = 'desc'
        search_params = dict()
        search_headers = {'content-type': 'application/x-www-form-urlencoded'}
        search_headers.update(self.session.headers)

        """
        /api/2.0/recording?
        cause[]=fullTimeRecording
        cause[]=motionRecording
        startTime=1538719200000
        endTime=1538805600000
        cameras[]=5b8f55509008007bce929a0f
        cameras[]=5b8f55509008007bce929a0b
        cameras[]=5b8f55509008007bce929a0d
        idsOnly=true
        sortBy=startTime
        sort=desc
        """

        # Don't include motion recording for now, it's redundant
        # search_params['cause[]'] = 'motionRecording'
        # We want just full time recordings
        search_params['cause[]'] = 'fullTimeRecording'

        # Start time
        search_params['startTime'] = epoch_start
        # End time
        search_params['endTime'] = epoch_end

        # Append list of camera IDs
        search_params['cameras[]'] = camera_id_list

        # Add the other misc. items
        search_params.update({'idsOnly': idsOnly, 'sortBy': sortBy, 'sort': sort})
        # pprint(search_params, indent=4)

        # Prepare the search data
        req = requests.Request('GET', f"{self.url}/api/2.0/recording", params=search_params, headers=search_headers,
                               cookies=self.session.cookies)
        prepped = req.prepare()

        # pprint(prepped.url, indent=4)

        # Send the search data
        r = self.session.send(prepped)

        if r.status_code is 200:
            clip_id_data = r.json()
        elif r.status_code is 401:
            self.logger.critical(f'Unauthorized, exiting.')
            sys.exit(1)
        else:
            self.logger.critical(f'An error occured: {r.status_code}')
            sys.exit(1)

        # pprint(r.json()['data'], indent=4)

        # Get clip meta data
        self.clip_meta_data(r.json()['data'])

        # pprint(self.dict_info_clip, indent=4)


    def download_footage(self, output_path= Path('downloaded_clips')):
        """
        - Search for footage & get ID values
        - Try to get the sizes for each clip
        - Download each clip on it's own
        - Name the clip and save it to disk in a folder for each camera
        """
        example = "/api/2.0/recording/5bb829e4b3a28701fe50b258/download"
        meta_cookies = {'cameras.isManagedFilterOn': 'false'}
        meta_cookies.update(self.session.cookies)
        # num_clips = len(self.clip_meta_data)
        url_id_params = str()

        # Create output if it doesn't exist yet
        self.outputPathCheck(output_path)

        # pprint(self.dict_info_clip, indent=4)

        # Dict of files to download
        for count, clip in enumerate(self.dict_info_clip, 1):
            # Show which video we are on out of the total number of videos
            click.secho(f'[*] Downloading {count} of {len(self.dict_info_clip)} videos.', bold=True)
            # print(f"{self.url}/api/2.0/recording/{self.dict_info_clip[clip].clip_id}/download")
            req = requests.Request('GET', f"{self.url}/api/2.0/recording/{self.dict_info_clip[clip].clip_id}/download", cookies=meta_cookies)
            prepped = req.prepare()
            # print(prepped.url)
            self.logger.debug(f'Attempting to download clip {self.dict_info_clip[clip].clip_id}')

            r = self.session.send(prepped, stream=True)

            if r.status_code is 200:
                self.logger.debug(f'Successfully requested clip {self.dict_info_clip[clip].clip_id}')
            elif r.status_code is 401:
                self.logger.critical(f'Unauthorized, exiting.')
                sys.exit(1)
            else:
                self.logger.critical(f'Unexpected error occured: {r.status_code}. Exiting.')
                pprint(r.text)
                sys.exit(1)

            total = r.headers.get('Content-Length')
            num_chunks = round(int(total) / self.chunk_size)

            file_path = Path(output_path, self.dict_info_clip[clip].cameraName.replace(' ', '_'), self.dict_info_clip[clip].fullFileName)
            if not file_path.parent.exists():
                file_path.parent.mkdir(exist_ok=True)

            with open(file_path , 'wb') as f:
                with click.progressbar(r.iter_content(chunk_size=self.chunk_size), length=num_chunks, label=f'Downloading Video {self.dict_info_clip[clip].fullFileName}', show_percent=True, show_eta=False) as bar:
                    for data in bar:
                        f.write(data)
            self.logger.info(f'Done downloading file {self.dict_info_clip[clip].clip_id}')


    def outputPathCheck(self, output_path):
        """
        Check if the path exists
        """
        if not output_path.is_dir() and output_path.exists():
            self.logger.critical(f'Output path {output_path} is not a directory but it exists, specify a directory.')
            sys.exit(1)
        elif not output_path.exists():
            # Make the output path
            self.logger.debug('Creating output directories')
            output_path.mkdir(exist_ok=False)

        elif output_path.is_dir():
            # Don't over write existing directories, for now
            self.logger.critical('Output directory already exists')
            sys.exit(1)
