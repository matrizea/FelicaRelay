from time import sleep
import nfc
from nfc.clf import RemoteTarget, LocalTarget, TimeoutError, BrokenLinkError
import argparse
from time import time
fromhex = bytearray.fromhex

parser = argparse.ArgumentParser(description='Relay felica exchange.')


parser.add_argument('-l', '--log', action='store_true',
                    help='show nfc.clf log')
parser.add_argument('-t', '--timeout', type=float, default=0.005,
                    help='exchange timeout (default: 0.005s)')
parser.add_argument('-r', '--replace', nargs=2, metavar=('OLD', 'NEW'),  # action="append", default=list(),
                    help='replace exchange')
parser.add_argument('-d', '--replace-decimal', nargs=2, metavar=('OLD', 'NEW'), type=int,
                    help='replace exchange decimal')
parser.add_argument('-e', '--replace-text', nargs=2, metavar=('OLD', 'NEW'),
                    help='replace exchange text')
parser.add_argument('-s', '--system-code',
                    help='polling system code (default: FFFF)', default='FFFF')

args = parser.parse_args()

LOG = args.log

TIMEOUT = args.timeout
print('TIMEOUT', TIMEOUT, 's')
TIMEOUT_R = TIMEOUT_E = TIMEOUT

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

print('devices', devices)

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
    print(idm.hex(), pmm.hex(), sys.hex())

    sensf_res = b'\x01' + idm + pmm + sys

    print('sensf_res', sensf_res.hex())

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
    print(time(), 'Response from Reader:', rsp_e.hex(), sep='\t')

    idm = int.from_bytes(tag_r.idm, "big")

    while True:
        try:  # Card <-> my R/W
            rsp_r = clf_r.exchange(rsp_e, TIMEOUT_R)
            print(time(), 'Response from Card\t', rsp_r.hex(), sep='\t')
            if REPLACE:
                if REPLACE[0] in rsp_r.hex():
                    print('Replaced')
                rsp_r = fromhex(rsp_r.hex().replace(REPLACE[0], REPLACE[1]))
            if REPLACE_TEXT:
                rsp_r = rsp_r.replace(REPLACE_TEXT[0], REPLACE_TEXT[1])

        except TimeoutError:
            rsp_r = None
            print('TIMEOUT Card')

        try:  # Emu <-> Reader/Writer
            rsp_e = clf_e.exchange(rsp_r, TIMEOUT_E)
            print(time(), 'Response from Reader\t', rsp_e.hex(), sep='\t')

        except TimeoutError:
            print('TIMEOUT Reader')
        except BrokenLinkError:
            print('Exchange Finished')
            clf_r.close()
            clf_e.close()
            break
