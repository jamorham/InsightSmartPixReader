#!/usr/bin/python
#
# smart pix insight nightscout uploader
# jamorham + cjo20
#
# Provided on an 'as is' basis. Any use is entirely at your own risk.


def cry_about_module(mod):
    print "Cannot import " + mod + " module!"
    print
    print "try: sudo pip install " + mod
    print "if you don't have pip then try first:"
    print "sudo apt-get install python-pip"
    print "if that doesn't work try: "
    print "sudo apt-get install python-" + mod
    print
    exit(5)


try:
    import logging
except ImportError:
    cry_about_module("logging")

try:
    from pytz import timezone
except ImportError:
    cry_about_module("pytz")

try:
    from tzlocal import get_localzone
except ImportError:
    cry_about_module("tzlocal")

try:
    import datetime
except ImportError:
    cry_about_module("datetime")

try:
    from dateutil import parser
    from dateutil.tz import tzlocal
    from dateutil.tz import gettz
except ImportError:
    cry_about_module("dateutil")

try:
    import xmltodict
except ImportError:
    cry_about_module("xmtodict")

try:
    import argparse
except ImportError:
    cry_about_module("argparse")
try:
    import requests
except ImportError:
    cry_about_module("requests")

try:
    import json
except ImportError:
    cry_about_module("json")

try:
    import hashlib
except ImportError:
    cry_about_module("hashlib")

import os, time

####################################################################

# Timezone is really important, this is whatever you are going to use
# with your meter. So if you adjust your meter for daylight saving times
# then be sure to include your region like Europe/London if you always keep it
# fixed to a specific timezone then set it like UTC-5 for 5 hours behind GMT/UTC
# if this is incorrect then your blood test values etc are going to be in the wrong place
# which will cause chaos. If your meter clock can't be matched accurately enough against
# the computer time then it will refuse to process the data.

# where the device appears on your system
DEVICE = "/dev/disk/by-label/SMART_PIX2"

# it will try to use sudo to allow you mount this via fstab
TEMP_FOLDER = "/tmp/smartpix"

# where to log what happens, make sure its writable
LOG_FILE = "/tmp/smart-pix-reader.log"

# maximum wait time in seconds for scan to complete
# note it can take up to 4 minutes possibly more!
MAX_WAIT_TIME = 240
MAX_TIME_DIFF_SECONDS = 120

###################################################################
MISC_FOLDER = TEMP_FOLDER + "/" + "MISC" + "/"
STATUS_FILE = MISC_FOLDER + "STATUS" + ".TXT"
AUTOSCAN_FILE = MISC_FOLDER + "AUTOSCAN" + ".TXT"
DEVLIST_FILE = MISC_FOLDER + "DEVLIST" + ".XML"

STARTUP_SECONDS = 20  # probably a bad idea to change this

recursion = 0
last_status = "startup"


class BreakException(Exception):
    pass


def enableRelay(relaypin, state):
    relaypin = int(relaypin)
    if relaypin == 0:
        return
    logger.debug("Setting relay on pin " + str(relaypin) + " to state " + str(state))
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(relaypin, GPIO.OUT)
        GPIO.output(relaypin, not state)  # low = on
    except ImportError:
        logger.error("Could not import Rpi.GPIO are you running on a raspberry pi?")


def waitForPir(pirpin):
    pirpin = int(pirpin)
    if (pirpin == 0):
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pirpin, GPIO.IN)
        # GPIO.setup(pirpin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        if GPIO.input(pirpin) == GPIO.HIGH:
            logger.info("Waiting for motion sensor to report motion has stopped")
            while GPIO.input(pirpin) == GPIO.HIGH:
                logger.debug("Motion sensor still reporting motion")
                time.sleep(10)

    except ImportError:
        logger.error("Could not import Rpi.GPIO are you running on a raspberry pi?")


def checkFstab():
    global recursion
    recursion += 1
    if os.geteuid() != 0:
        if os.path.exists(DEVICE):
            if not DEVICE in open("/etc/fstab").read():
                print
                print
                print "We need to use root to add the fstab mount entry for the Smart Pix device"
                print
                print
                os.system(
                    "sudo sh -c \"echo '\n" + DEVICE + " " + TEMP_FOLDER + " vfat user,sync,nosuid,noauto 0 0\n' >>/etc/fstab\"")
                if (recursion < 5):
                    checkFstab()


def getFile(the_file):
    try:
        with open(the_file) as f:
            content = f.readlines()
            content = [x.strip() for x in content]
            return content
    except IOError:
        logger.error("Got IO error reading: " + the_file)


def parseStatus():
    global last_status
    content = getFile(STATUS_FILE)
    this_status = (content[0].strip('\0'))
    if this_status != last_status and len(this_status) > 5:
        logger.info("Pix status: " + this_status)
        last_status = this_status
    try:
        status = content[2].split("-")[1]
    except:
        status = "unknown  please wait"
    return status


def mountPixFolder():
    logger.debug("Attempting to mount folder")
    os.system("umount 2>/dev/null " + TEMP_FOLDER)
    os.system("umount 2>/dev/null " + DEVICE)
    if not os.path.exists(TEMP_FOLDER):
        os.mkdir(TEMP_FOLDER)
    os.system("mount " + DEVICE)

    if not os.path.exists(STATUS_FILE):
        logger.error("Mount failed, could not find status file!")
        exit(5)


def unmountPix():
    if (not args.debug):
        os.system("umount 2>/dev/null " + TEMP_FOLDER)
        os.system("umount 2>/dev/null " + DEVICE)


def createNightScoutBasalRecord(nextdttm, dttm, cbrf, profile, remark, maxage=86400 * 14):
    basaldttm = mytimezone.localize(parser.parse(dttm))
    timestamp = int((basaldttm - datetime.datetime(1970, 1, 1).replace(tzinfo=timezone("UTC"))).total_seconds()) * 1000

    basaldttmend = mytimezone.localize(parser.parse(nextdttm))
    timestamp_end = int(
        (basaldttmend - datetime.datetime(1970, 1, 1).replace(tzinfo=timezone("UTC"))).total_seconds()) * 1000

    durationmins = int((timestamp_end - timestamp) / 60000)

    if (args.debug):
        print "BASAL: start: " + dttm + " end: " + nextdttm + " duration: " + str(durationmins) + " mins"

    if (time.time() - (timestamp / 1000) > maxage):
        return

    if (durationmins < 0):
        logger.info("Ignoring record with negative duration: " + dttm + " " + nextdttm)
        return

    timestamp_dt = datetime.datetime.fromtimestamp(timestamp / 1000).replace(tzinfo=timezone("UTC"))
    payload = {}

    payload['enteredBy'] = deviceid
    payload['date'] = timestamp
    payload['dateString'] = timestamp_dt.isoformat()
    payload['created_at'] = timestamp_dt.isoformat()
    payload['sysTime'] = timestamp_dt.isoformat()
    payload['eventType'] = "Temp Basal"
    payload['duration'] = int(durationmins)
    payload['absolute'] = float(cbrf)

    if (len(remark) > 0):
        payload['notes'] = remark

    return payload


def createNightScoutTreatmentRecord(bgdtstr, bg, bgunit, carbs, insulin, event, maxage=86400 * 14, notes=""):
    if carbs == 0 and bg == 0 and insulin == 0 and event == 0 and notes == "":
        return

    bgdt = mytimezone.localize(parser.parse(bgdtstr))

    timestamp = int((bgdt - datetime.datetime(1970, 1, 1).replace(tzinfo=timezone("UTC"))).total_seconds()) * 1000

    if (time.time() - (timestamp / 1000) > maxage):
        # print "Over max age: "+bgdtstr
        return

    nightscout_unit = "mgdl"
    nightscout_bg = bg

    if (bgunit == "mmol/L"):
        bg = float(bg)
        bg *= 18.018018
        bg = int(bg)
        nightscout_unit = "mmol"

    timestamp_dt = datetime.datetime.fromtimestamp(timestamp / 1000).replace(tzinfo=timezone("UTC"))

    payload = {}
    if (bg > 0):
        payload['glucoseType'] = "Finger"
        payload['units'] = nightscout_unit
        payload['glucose'] = nightscout_bg

    if (carbs > 0):
        payload['carbs'] = carbs

    if (insulin > 0):
        payload['insulin'] = insulin

    # TODO humanize events
    if (event > 0):
        notes += "Event: " + str(event)

    if (len(notes) > 0):
        payload['notes'] = notes

    payload['enteredBy'] = deviceid
    payload['date'] = timestamp
    payload['dateString'] = timestamp_dt.isoformat()
    payload['created_at'] = timestamp_dt.isoformat()
    payload['sysTime'] = timestamp_dt.isoformat()

    return payload


# setup logging

logging.basicConfig(filename=LOG_FILE, format='%(asctime)s %(levelname)s: %(message)s', level=logging.DEBUG)
logger = logging.getLogger('smart-pix-reader')
logger.setLevel(logging.INFO)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s : %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)

# main code

arg_parser = argparse.ArgumentParser(
    description="Smart Pix reader - designed for Insight pump/handset.  Can upload data to Nightscout and trigger xDrip+ calibrations.  Any use is entirely at your own risk, code provided on an 'AS IS' basis only. Not endorsed by any equipment manfacturer.")
arg_parser.add_argument('--base_url', help="Base URL of Nightscout site", required=True)
arg_parser.add_argument('--api_secret', help="API-SECRET for uploading", required=True)
arg_parser.add_argument('--meter_serial', help="Restrict to meter serial number", required=False)
arg_parser.add_argument('--constant', help="Run constantly looking for new data", default=False, action='store_true')
arg_parser.add_argument('--skip_reload', help="Don't reload new data from the device", default=False,
                        action='store_true')
arg_parser.add_argument('--debug', action='store_true')
arg_parser.add_argument('--relay_pin', help="Specify which GPIO pin an optional relay is connected", default=0)
arg_parser.add_argument('--motion_pin', help="Specify which GPIO pin an optional motion sensor is connected to",
                        default=0)
arg_parser.add_argument('--timezone', default=str(get_localzone()),
                        help="Timezone to use if not " + str(get_localzone()) + " eg: Europe/London")

args = arg_parser.parse_args()

if args.debug:
    console.setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)

checkFstab()

nightscout_secret_hash = hashlib.sha1(args.api_secret).hexdigest()
reload = not args.skip_reload

if args.meter_serial is None:
    METER_SERIAL = ""
else:
    METER_SERIAL = args.meter_serial

TIMEZONE = args.timezone
mytimezone = timezone(TIMEZONE)

logger.debug("Startup, Timezone: " + TIMEZONE)

if not os.path.exists(DEVICE):
    logger.error("Cannot find the Smart Pix device on your system")
    exit(5)

logger.debug("Smart Pix Device found")

keepRunning = True
last_scan_time = 0.0

# how frequently to probe if we get errors
MAX_SCAN_FREQ = 300
# how long to wait after we get successful data to avoid constantly downloading
WAIT_BETWEEN_SUCCESSES = 1800

while keepRunning:
    global processing_seconds
    processing_seconds = 0

    try:
        if not args.constant:
            keepRunning = False  # only go one time
        waitForPir(args.motion_pin)
        if (args.relay_pin > 0):
            enableRelay(args.relay_pin, True)
        mountPixFolder()
        if (reload):
            scan_delay = time.time() - last_scan_time
            while (scan_delay < MAX_SCAN_FREQ):
                logger.info("Waiting to scan " + str(int((MAX_SCAN_FREQ - scan_delay) / 60)) + " minutes left")
                time.sleep(60)
                scan_delay = time.time() - last_scan_time
            last_scan_time = time.time()
            logger.info("Requesting new data - this can take several minutes")

            asf = open(AUTOSCAN_FILE, "w")
            written = asf.write(
                "\x53\x4c\x34\x32\x2d\x42\x20\x52\x65\x6d\x6f\x74\x65\x43\x6f\x6e\x74\x72\x6f\x6c\x20\x46\x69\x6c\x65\x0a\x43\x6f\x6d\x6d\x61\x6e\x64\x3d\x41\x75\x74\x6f\x53\x63\x61\x6e")
            asf.flush()
            asf.close()

            logger.debug("Wrote characters to autoscan file")

            # wait for processing
            last_pix_status = ""
            pix_status = ""
            time_start = time.time()
            while time.time() - time_start < STARTUP_SECONDS or (
                        not (
                                        pix_status == "done" or pix_status == "failed") and time.time() - time_start < MAX_WAIT_TIME):
                pix_status = parseStatus()
                if not pix_status == last_pix_status:
                    if (time.time() - time_start > STARTUP_SECONDS or pix_status != "done"):
                        logger.info("Status changed to: " + pix_status)
                    last_pix_status = pix_status

                time.sleep(0.5)

            if pix_status == "failed":
                logger.error("Scan failed - check the meter connected to the smart pix device!")
                unmountPix()
                raise BreakException

            if not pix_status == "done":
                logger.error("Timed out after " + str(MAX_WAIT_TIME) + " seconds waiting for scan to complete")
                if (pix_status.startswith("unknown")):
                    logger.error("Status error - check the meter connected to the smart pix device?")
                unmountPix()
                raise BreakException

            # we got some data
            processing_seconds = int(time.time() - time_start)
            logger.info("Scan complete after: " + str(processing_seconds) + " seconds")

        with open(DEVLIST_FILE) as fd:
            try:
                doc = xmltodict.parse(fd.read())
                if not 'DEVICE' in doc['DEVICELIST']:
                    logger.error("No device data available - try again")
                    exit(5)

                serial = doc['DEVICELIST']['DEVICE']['SERIALNR']
                dclass = doc['DEVICELIST']['DEVICE']['CLASS']
                name = doc['DEVICELIST']['DEVICE']['NAME']
                deviceid = name + " " + serial

                logger.debug(dclass + " serial number is: " + serial + " name " + name)

                if (METER_SERIAL != "" and serial != METER_SERIAL):
                    logger.error("Meter serials do not match: " + METER_SERIAL + " vs " + serial)
                    exit(5)

                GLUCOSE_FILE = MISC_FOLDER + "G" + serial[1:] + ".XML"
                if not os.path.exists(GLUCOSE_FILE):
                    logger.error("Could not find glucose data file for meter: " + METER_SERIAL + " try re-running?")
                    exit(7)

                with open(GLUCOSE_FILE) as gd:
                    gd = xmltodict.parse(gd.read())
                    imp = gd['IMPORT']
                    gdev = imp['DEVICE']
                    pairing = gdev['PAIRING']
                    pumpserial = pairing['@PumpSerialNr']
                    logger.debug("      Paired with pump: " + pumpserial)
                    dt = gdev['@Dt']
                    tm = gdev['@Tm']
                    bgunit = gdev['@BGUnit']
                    logger.debug("Device time is: " + dt + " " + tm)

                    meterdt = mytimezone.localize(parser.parse(dt + " " + tm))
                    logger.debug("Meter date time: " + str(meterdt))
                    hostdt = datetime.datetime.now(mytimezone)
                    logger.debug(" Host date time: " + str(hostdt))
                    timediff = hostdt - meterdt

                    adjusted_timediff_seconds = timediff.seconds - (processing_seconds - STARTUP_SECONDS)
                    logger.debug("Adjusted clock difference: " + str(adjusted_timediff_seconds) + " seconds")
                    # handle daylight saving time
                    if (
                                    reload and adjusted_timediff_seconds > MAX_TIME_DIFF_SECONDS or adjusted_timediff_seconds < -60):
                        logger.error(
                            "Meter time is more than " + str(
                                MAX_TIME_DIFF_SECONDS) + " seconds different to ours. (" + str(
                                adjusted_timediff_seconds) + "s)")
                        logger.critical("Please check the meter clock, refusing to proceed!")
                        exit(6)
                    # profile_timeblocks = imp['TIMEBLOCKS']
                    bgdata = imp['BGDATA']['BG']

                    payload_list = []

                    # process bgdata entries

                    for i in range(0, len(bgdata)):
                        last = bgdata[i]
                        event = 0
                        carbs = 0
                        insulin = 0
                        bg = 0.0
                        dttm = last['@Dt'] + " " + last['@Tm']
                        if last['@Val'] != "---" and float(last['@Val'] > 0):
                            bg = float(last['@Val'])
                        if '@Carb' in last:
                            carbs = int(last['@Carb'])
                        if '@Evt' in last:
                            event = int(last['@Evt'])

                        payload = createNightScoutTreatmentRecord(dttm, bg, bgunit, carbs, insulin, event)
                        if (not payload is None and len(payload) > 0):
                            payload_list.append(payload)

                    # process pump data
                    PUMPFILE = MISC_FOLDER + "I" + pumpserial[1:] + ".XML"
                    if not os.path.exists(PUMPFILE):
                        logger.error("Cannot find pump data file for pump: " + pumpserial + " " + PUMPFILE)
                        exit(8)

                    with open(PUMPFILE) as id:
                        idx = xmltodict.parse(id.read())
                        iimp = idx['IMPORT']
                        bolusdata = iimp['IPDATA']['BOLUS']
                        basaldata = iimp['IPDATA']['BASAL']
                        eventdata = iimp['IPDATA']['EVENT']

                        # boluses
                        for i in range(0, len(bolusdata)):
                            bi = bolusdata[i]
                            if bi['@Tm'] != "":
                                dttm = bi['@Dt'] + " " + bi['@Tm']
                                btype = bi['@type']
                                insulin = bi['@amount']
                                notes = ""
                                if len(btype) > 0:
                                    notes = "Bolus " + btype
                                payload = createNightScoutTreatmentRecord(dttm, 0, 0, 0, insulin, 0, notes=notes)
                                if (not payload is None and len(payload) > 0):
                                    payload_list.append(payload)
                                    # else:
                                    # not handling daily totals yet
                                    # print bi

                        # TODO consolidate records

                        # events
                        for i in range(0, len(eventdata)):
                            ei = eventdata[i]
                            dttm = ei['@Dt'] + " " + ei['@Tm']
                            if '@description' in ei:
                                notes = ei['@description']
                            else:
                                notes = ""
                            if '@shortinfo' in ei:
                                notes += " (" + ei['@shortinfo'] + ")"
                            payload = createNightScoutTreatmentRecord(dttm, 0, 0, 0, 0, 0, notes=notes)
                            if (not payload is None and len(payload) > 0):
                                payload_list.append(payload)

                        # basal
                        firstbasal = True
                        for i in reversed(range(0, len(basaldata))):
                            bi = basaldata[i]
                            dttm = bi['@Dt'] + " " + bi['@Tm']
                            if (not firstbasal):
                                payload = createNightScoutBasalRecord(dttm, lastdttm, cbrf, profile, remark)
                                if (not payload is None and len(payload) > 0):
                                    payload_list.append(payload)
                            cbrf = bi['@cbrf']
                            profile = ""
                            if '@profile' in bi:
                                profile = bi['@profile']
                            remark = ""
                            if '@remark' in bi:
                                remark = bi['@remark']

                            firstbasal = False
                            lastdttm = dttm

                            # TODO process last if it is a TBR start
                            # TODO process from TBR starts to TBR ends
                            # TODO define profile from settings

                    logger.debug("Starting upload")

                    headers = {'Content-Type': "application/json", 'Accept': 'application/json',
                               'API-SECRET': nightscout_secret_hash}
                    upload_start = time.time()
                    try:
                        result = requests.post(url="%s/api/v1/treatments" % args.base_url, headers=headers,
                                               data=json.dumps(payload_list))

                        if (result.status_code == 200):
                            logger.info("Uploaded " + str(len(payload_list)) + " records successfully in " + str(
                                int(time.time() - upload_start)) + " seconds")
                            if args.constant:
                                if (args.relay_pin > 0):
                                    logger.debug("Delaying before switching off relay")
                                    time.sleep(20)
                                    enableRelay(args.relay_pin, False)
                                logger.info("Waiting for " + (
                                    str(int(WAIT_BETWEEN_SUCCESSES / 60))) + " minutes due to success")
                                time.sleep(WAIT_BETWEEN_SUCCESSES)

                        else:
                            logger.error("Upload error status: %d" % result.status_code)
                            logger.error("  Upload error text: %s" % result.text)
                    except requests.exceptions.ConnectionError as e:
                        logger.error("Upload connection error: " + str(e))
            except BreakException:
                logger.debug("Got break exception")

            except Exception as e:
                logger.error("Got error during processing: " + str(e))

            finally:
                unmountPix()
    except BreakException:
        logger.debug("Got outer break exception")
