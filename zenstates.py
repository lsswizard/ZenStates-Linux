#!/usr/bin/python
import struct
import os
import glob
import argparse

# Define the range for P-States MSRs
pstates = range(0xC0010064, 0xC001006C)

# Function to write to an MSR (Model Specific Register)
def writemsr(msr, val, cpu=-1):
    try:
        if cpu == -1:
            for c in glob.glob('/dev/cpu/[0-9]*/msr'):
                with os.fdopen(os.open(c, os.O_WRONLY), 'wb') as f:
                    f.seek(msr)
                    f.write(struct.pack('Q', val))
        else:
            with os.fdopen(os.open(f'/dev/cpu/{cpu}/msr', os.O_WRONLY), 'wb') as f:
                f.seek(msr)
                f.write(struct.pack('Q', val))
    except Exception as e:
        raise OSError("MSR module not loaded (run 'modprobe msr')") from e

# Function to read from an MSR
def readmsr(msr, cpu=0):
    try:
        with os.fdopen(os.open(f'/dev/cpu/{cpu}/msr', os.O_RDONLY), 'rb') as f:
            f.seek(msr)
            val = struct.unpack('Q', f.read(8))[0]
        return val
    except Exception as e:
        raise OSError("MSR module not loaded (run 'modprobe msr')") from e

# Function to convert a P-State value to a readable string
def pstate2str(val):
    if val & (1 << 63):
        fid = val & 0xff
        did = (val & 0x3f00) >> 8
        vid = (val & 0x3fc000) >> 14
        ratio = 25 * fid / (12.5 * did)
        vcore = 1.55 - 0.00625 * vid
        return f"Enabled - FID = {fid:X} - DID = {did:X} - VID = {vid:X} - Ratio = {ratio:.2f} - vCore = {vcore:.5f}"
    else:
        return "Disabled"

# Function to set specific bits within a value
def setbits(val, base, length, new):
    mask = (1 << length) - 1
    return (val & ~(mask << base)) | (new << base)

# Functions to set specific fields within a P-State
def setfid(val, new):
    return setbits(val, 0, 8, new)

def setdid(val, new):
    return setbits(val, 8, 6, new)

def setvid(val, new):
    return setbits(val, 14, 8, new)

# Function to calculate VID from vCore
def vcore_to_vid(vcore):
    return int(round((1.55 - vcore) / 0.00625))

# Function to parse hex values
def hex(x):
    return int(x, 16)

# Argument parser setup
parser = argparse.ArgumentParser(description='Sets P-States for Ryzen processors')
parser.add_argument('-l', '--list', action='store_true', help='List all P-States')
parser.add_argument('-p', '--pstate', default=-1, type=int, choices=range(8), help='P-State to set')
parser.add_argument('--enable', action='store_true', help='Enable P-State')
parser.add_argument('--disable', action='store_true', help='Disable P-State')
parser.add_argument('-f', '--fid', default=-1, type=hex, help='FID to set (in hex)')
parser.add_argument('-d', '--did', default=-1, type=hex, help='DID to set (in hex)')
parser.add_argument('-v', '--vid', default=-1, type=hex, help='VID to set (in hex)')
parser.add_argument('--vcore', default=-1, type=float, help='vCore to set (in volts)')
parser.add_argument('--c6-enable', action='store_true', help='Enable C-State C6')
parser.add_argument('--c6-disable', action='store_true', help='Disable C-State C6')

# Parse the arguments
args = parser.parse_args()

# List all P-States
if args.list:
    for p in range(len(pstates)):
        print(f'P{p} - {pstate2str(readmsr(pstates[p]))}')
    print('C6 State - Package - ' + ('Enabled' if readmsr(0xC0010292) & (1 << 32) else 'Disabled'))
    print('C6 State - Core - ' + ('Enabled' if readmsr(0xC0010296) & ((1 << 22) | (1 << 14) | (1 << 6)) == ((1 << 22) | (1 << 14) | (1 << 6)) else 'Disabled'))

# Set a specific P-State
if args.pstate >= 0:
    new = old = readmsr(pstates[args.pstate])
    print(f'Current P{args.pstate}: {pstate2str(old)}')
    if args.enable:
        new = setbits(new, 63, 1, 1)
        print('Enabling state')
    if args.disable:
        new = setbits(new, 63, 1, 0)
        print('Disabling state')
    if args.fid >= 0:
        new = setfid(new, args.fid)
        print(f'Setting FID to {args.fid:X}')
    if args.did >= 0:
        new = setdid(new, args.did)
        print(f'Setting DID to {args.did:X}')
    if args.vid >= 0:
        new = setvid(new, args.vid)
        print(f'Setting VID to {args.vid:X}')
    if args.vcore >= 0:
        vid = vcore_to_vid(args.vcore)
        actual_vcore = 1.55 - vid * 0.00625
        new = setvid(new, vid)
        print(f'Setting vCore to {actual_vcore:.5f}V (VID = {vid:X})')
    if new != old:
        if not (readmsr(0xC0010015) & (1 << 21)):
            print('Locking TSC frequency')
            for c in range(len(glob.glob('/dev/cpu/[0-9]*/msr'))):
                writemsr(0xC0010015, readmsr(0xC0010015, c) | (1 << 21), c)
        print(f'New P{args.pstate}: {pstate2str(new)}')
        writemsr(pstates[args.pstate], new)

# Enable C6 State
if args.c6_enable:
    writemsr(0xC0010292, readmsr(0xC0010292) | (1 << 32))
    writemsr(0xC0010296, readmsr(0xC0010296) | ((1 << 22) | (1 << 14) | (1 << 6)))
    print('Enabling C6 state')

# Disable C6 State
if args.c6_disable:
    writemsr(0xC0010292, readmsr(0xC0010292) & ~(1 << 32))
    writemsr(0xC0010296, readmsr(0xC0010296) & ~((1 << 22) | (1 << 14) | (1 << 6)))
    print('Disabling C6 state')

# If no arguments are provided, display help
if not args.list and args.pstate == -1 and not args.c6_enable and not args.c6_disable:
    parser.print_help()
