# UVC_Client
A CLI app that logs into a Ubiquity Unified Video Controller and downloads videos in a date time range. 

* Install with `pip3 install requests click pendulum`
* Run with `python3 unifi-video-client.py -s 01-01-2019:15:00:00 -e 25-12-2018:23:30:00 -u admin -d uvc-controller.local -tz "America/Denver" -o camera-download-dir/ "Camera 1"`