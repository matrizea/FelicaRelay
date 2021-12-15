from time import sleep
import nfc
from nfc.clf import RemoteTarget, LocalTarget, TimeoutError, BrokenLinkError
import argparse
import json
from time import time
fromhex = bytearray.fromhex

parser = argparse.ArgumentParser(
    description='Relay felica exchange.', epilog='v2.1',
    formatter_class=argparse.RawTextHelpFormatter)


parser.add_argument('-l', '--log', action='store_true',
                    help='show nfc.clf log')
parser.add_argument('-t', '--timeout', type=float, default=0.005,
                    help='exchange timeout (default: 0.005s)')
parser.add_argument('--timeout-card', type=float,
                    help='card exchange timeout')
parser.add_argument('--timeout-reader', type=float,
                    help='reader exchange timeout')
parser.add_argument('-r', '--replace', nargs=2, metavar=('OLD', 'NEW'),  # action="append", default=list(),
                    help='replace exchange')
parser.add_argument('-d', '--replace-decimal', nargs=2, metavar=('OLD', 'NEW'), type=int,
                    help='replace exchange decimal')
parser.add_argument('-e', '--replace-text', nargs=2, metavar=('OLD', 'NEW'),
                    help='replace exchange text')
parser.add_argument('-s', '--system-code',
                    help='polling system code (default: FFFF)', default='FFFF')
parser.add_argument('--ignore-polling', action='store_true',
                    help='ignore reader polling')
parser.add_argument('--device-card',
                    help='card device')
parser.add_argument('--device-reader',
                    help='reader device')
parser.add_argument('--show-time', action='store_true',
                    help='show command response time\nno compatibility with FelicaReplay')
parser.add_argument('--block-write-response', action='store_true',
                    help='block card write response')

args = parser.parse_args()

LOG = args.log

TIMEOUT = args.timeout
TIMEOUT_R = TIMEOUT_E = TIMEOUT
if args.timeout_card is not None:
    TIMEOUT_R = args.timeout_card
print('TIMEOUT CARD  ', TIMEOUT_R, 's')
if args.timeout_reader is not None:
    TIMEOUT_E = args.timeout_reader
print('TIMEOUT READER', TIMEOUT_E, 's')


REPLACE = args.replace
if REPLACE:
    REPLACE = REPLACE[0].lower(), REPLACE[1].lower()

if args.replace_decimal:
    do, dn = args.replace_decimal
    assert 0 <= do < 0x10000 and 0 <= dn < 0x10000
    ro = '%02x%02x' % (do % 0x100, do // 0x100)
    rn = '%02x%02x' % (dn % 0x100, dn // 0x100)
    REPLACE = (ro, rn)

REPLACE_TEXT = None
if args.replace_text:
    to, tn = args.replace_text
    REPLACE_TEXT = (to.encode(), tn.encode())

if len(args.system_code) != 4:
    print('Illegal System Code')
    exit(-1)

system_code = int(args.system_code, 16)


IGNORE_POLLING = args.ignore_polling

DEVICE_CARD = args.device_card
DEVICE_READER = args.device_reader

if DEVICE_CARD or DEVICE_READER:
    if not (DEVICE_CARD and DEVICE_READER):
        print('Specific both devices for now')
        exit(-1)

SHOW_TIME = args.show_time


BLOCK_WRITE_RESPONSE = args.block_write_response


def enablelogging():
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logging_level = logging.getLogger().getEffectiveLevel()
    logging.getLogger("nfc.clf").setLevel(logging_level)


def disablelogging():
    import logging
    logging.basicConfig(level=logging.ERROR)
    logging_level = logging.getLogger().getEffectiveLevel()
    logging.getLogger("nfc.clf").setLevel(logging_level)


# Card <-> [ R/W <-> relay <-> Emu ] <-> Reader/Writer
if DEVICE_CARD or DEVICE_READER:
    device_r, device_e = DEVICE_CARD, DEVICE_READER
else:
    print('Scanning Devices...')

    devices = []

    break_ = False
    for b in range(1, 10):
        for d in range(50):
            device = f'usb:{b:03d}:{d:03d}'
            try:
                nfc.ContactlessFrontend(device)
                devices.append(device)
                if len(devices) == 2:
                    break_ = True
                    break
            except OSError:
                pass
        if break_:
            break

    if len(devices) == 0:
        print('No Device')
        exit(-1)

    if len(devices) == 1:
        print('Not Enough Devices')
        exit(-1)

    assert len(devices) == 2

    if nfc.ContactlessFrontend(devices[0]).sense(RemoteTarget("212F")) is None:
        device_e, device_r = devices
    else:
        device_r, device_e = devices


print('DEVICE CARD  ', device_r)
print('DEVICE READER', device_e)

if LOG:
    enablelogging()

for _ in range(1):
    clf_r = nfc.ContactlessFrontend(device_r)
    clf_e = nfc.ContactlessFrontend(device_e)

    target_r = clf_r.sense(RemoteTarget("212F"))

    if target_r is None:
        print('No Card')
        exit(-1)

    print('target_r', target_r)

    tag_r = nfc.tag.activate(clf_r, target_r)

    print('Tag', tag_r)

    if isinstance(tag_r, nfc.tag.tt3_sony.FelicaStandard):
        print('Request System Code')
        for sys in tag_r.request_system_code():
            print('%04x' % sys, end=' ')
        print()

    print('Polling to %02x' % system_code)

    idm, pmm, sys = tag_r.polling(system_code=system_code, request_code=1)

    print('idm pmm sys')
    print('<>', json.dumps(
        {'idm': idm.hex(), 'pmm': pmm.hex(), 'sys': sys.hex()}))

    sensf_res = b'\x01' + idm + pmm + sys

    print('sensf_res', sensf_res.hex())

    print('Emulator Start')

    if LOG:
        target_e = clf_e.listen(LocalTarget(
            "212F", sensf_res=sensf_res), timeout=60.)
        if target_e is None:
            print('No Reader')
            exit(-1)
    else:
        target_e = None
        try:
            while target_e is None:
                target_e = clf_e.listen(LocalTarget(
                    "212F", sensf_res=sensf_res), timeout=.5)
        except KeyboardInterrupt:
            exit(-1)

    print('target_e', target_e)

    tt3_cmd = target_e.tt3_cmd
    rsp_e = (len(tt3_cmd) + 1).to_bytes(1, "big") + tt3_cmd

    print('Initial Response')
    if SHOW_TIME:
        print(time(), end='\t')
    print('<<', rsp_e.hex())

    idm = int.from_bytes(tag_r.idm, "big")

    while True:
        try:  # Card <-> my R/W
            rsp_r = clf_r.exchange(rsp_e, TIMEOUT_R)
            if REPLACE:
                if REPLACE[0] in rsp_r.hex():
                    print('Replaced')
                rsp_r = fromhex(rsp_r.hex().replace(REPLACE[0], REPLACE[1]))
            if REPLACE_TEXT:
                rsp_r = rsp_r.replace(REPLACE_TEXT[0], REPLACE_TEXT[1])
            if SHOW_TIME:
                print(time(), end='\t')
            print('>>', rsp_r.hex())

            if BLOCK_WRITE_RESPONSE:
                if rsp_r[1] == 0x17:
                    print('Blocking Write Response')
                    rsp_r = None

        except TimeoutError:
            rsp_r = None
            print('TIMEOUT Card')

        try:  # Emu <-> Reader/Writer
            while True:
                rsp_e = clf_e.exchange(rsp_r, TIMEOUT_E)
                if SHOW_TIME:
                    print(time(), end='\t')
                print('<<', rsp_e.hex())
                if rsp_e[1] == 0:
                    if IGNORE_POLLING:
                        print('Ignoring Polling')
                        rsp_r = None
                        continue
                break

        except TimeoutError:
            print('TIMEOUT Reader')
            break

        except BrokenLinkError:
            print('Exchange Finished')
            break

    clf_r.close()
    clf_e.close()
