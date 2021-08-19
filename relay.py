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
                    help='exchange timeout')
parser.add_argument('-r', '--replace', nargs=2, metavar=('OLD', 'NEW'),  # action="append", default=list(),
                    help='replace exchange')
parser.add_argument('-d', '--replace-decimal', nargs=2, metavar=('OLD', 'NEW'), type=int,
                    help='replace exchange decimal')
parser.add_argument('-s', '--system-code', help='specific system code')

args = parser.parse_args()

LOG = args.log

TIMEOUT = args.timeout
print('TIMEOUT', TIMEOUT, 's')
TIMEOUT_R = TIMEOUT_E = TIMEOUT

REPLACE = args.replace
REPLACE = REPLACE[0].lower(), REPLACE[1].lower()

if args.replace_decimal:
    do, dn = args.replace_decimal
    assert 0 <= do < 0x10000 and 0 <= dn < 0x10000
    ro = '%02x%02x' % (do % 0x100, do // 0x100)
    rn = '%02x%02x' % (dn % 0x100, dn // 0x100)
    REPLACE = (ro, rn)

if args.system_code:
    if len(args.system_code) != 4:
        print('Illegal System Code')
        exit(-1)
    sys_code = int(args.system_code, 16)
else:
    sys_code = None


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


if LOG:
    enablelogging()


# Card <-> [ R/W <-> relay <-> Emu ] <-> Reader/Writer

print('Scanning Devices...')

devices = []

for d in range(1000):
    device = 'usb:001:' + str(d).zfill(3)
    try:
        nfc.ContactlessFrontend(device)
        devices.append(device)
        if len(devices) >= 2:
            break
    except OSError:
        pass
    if d > 100:
        break

print('devices', devices)

if len(devices) < 2:
    print('Not Enough Devices')
    exit(-1)

if len(devices) > 2:
    print('Warning: Exceed Devices')

if nfc.ContactlessFrontend(devices[0]).sense(RemoteTarget("212F")) is None:
    device_e, device_r = devices[:2]
else:
    device_r, device_e = devices[:2]

for _ in range(1):
    clf_r = nfc.ContactlessFrontend(device_r)
    clf_e = nfc.ContactlessFrontend(device_e)

    if sys_code:
        target_r = clf_r.sense(RemoteTarget(
            "212F", sensf_req=fromhex('00%04x0000' % sys_code)))
    else:
        target_r = clf_r.sense(RemoteTarget("212F"))

    if target_r is None:
        print('No Card')
        exit(-1)

    print('target_r', target_r)

    tag_r = nfc.tag.activate(clf_r, target_r)
    print('Tag', tag_r)

    idm = tag_r.idm
    pmm = tag_r.pmm
    sys_i = tag_r.sys
    if sys_code:
        sys_i = sys_code

    sensf_res = b'\x01' + idm + pmm + sys_i.to_bytes(2, "big")
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
