# Smart Pix Insight Nightscout Uploader

## What this is for?

The script is designed to pull data from the Insight pump and handset when connected and to upload this data to Nightscout autonomously.

This includes, blood test results, insulin doses and pump events. (basal data soon)

Using xDrip+ connected to Nightscout via the standard Rest-API feature, the treatment data is then downloaded, so treatment simulations and automated opportunistic cgm calibration can occur.

Because the Insight handset can be set to "always connect to PC" and also charges while connected to the Smart Pix device, the data can be automatically synchronized simply by plugging the handset in to charge when it is not in use and data download occurs with no user operation required.

## What do I need?

This python script is designed to run on a Linux machine, typically a Raspberry Pi.

Connected to the Linux machine is the Smart Pix 2 interface device. The Insight pump handset is plugged in to this via its micro-usb charging connector.

## How do I set it up?

Plug the Smart Pix 2 device in to a USB port on your Linux machine

Plug the micro-usb cable from the Smart Pix in to the Insight Handset

Select `Connect to PC` on the Handset screen. Ideally select to always connect to PC without asking.

You'll need a Nightscout installation and to know your URL and API password

Download the `smart-pix-reader.py` script to your Linux machine


### Using the right Timezone!
In order to make sure the entries match the correct times in Nightscout you must be sure that you set the time on your Insight handset correctly.

* If you live in a region which uses daylight saving time and you manually change your Insight Handset clock to accurately reflect your local time then you should tell the script to use your local timezone.
* If you live in a region which doesn't use daylight saving time then you should also specify your local timezone.
* If, however, you don't adjust the clock on your handset when daylight saving time starts/finishes each year but you DO live in a region which uses daylight saving time then you need to specify the timezone as the offset from GMT/UTC that your pump handset has.

If you get this wrong then treatment entries in Nightscout are likely to appear at the wrong times and opportunistic calibration will be completely broken.

You also should make sure that your pump handset has the *exact* correct time as close as you can set it. The more accurate the clock is set on it, the more accurate any automated calibrations will be. Remember to promptly update your clock after daylight saving time transisitions.

Timezones might look like `Europe/London` or `America/New_York` for a region timezone. (see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones for a list)

For an absolute offset timezone where you don't change the clock for daylight saving time it would look more like `Etc/GMT+1` for 1 hour ahead of GMT/UTC.


## Example Usage

    python smart-pix-reader.py --base_url http://example.azurewebsites.net --api_secret mypassw0rd --timezone Europe/London

If there is any chance of a different handset being connected then you can lock it to work with only handset using the 8 digit serial number.

    python smart-pix-reader.py --meter_serial 00012345  --base_url http://example.azurewebsites.net \
                                                        --api_secret mypassw0rd --timezone Europe/London


# Disclaimer

Not for medical use. Any use of this software source code or information is entirely at your own risk, everything provided on an 'AS IS' basis only. Do not rely on this software, it could fail at any time.

Not endorsed or approved by any equipment manfacturer. All product names, etc are property of their respective owners. Any names used are for identification purposes only. Use of these names does not imply endorsement.