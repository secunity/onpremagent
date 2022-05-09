#!/usr/bin/env python3

from bin.shared import parse_config_vendor
from common.consts import PROGRAM
from common.enums import VENDOR
from common.utils import update_supervisor_program_autostart


def main():
    vendor, config = parse_config_vendor()
    if vendor == VENDOR.MIKROTIK:
        autostart_programs = [PROGRAM.FLOWS_SYNC, PROGRAM.FLOWS_APPLIER, PROGRAM.STATS_FETCHER]
    else:
        autostart_programs = [PROGRAM.STATS_FETCHER]

    for program in PROGRAM.ALL:
        autostart = program in autostart_programs
        update_supervisor_program_autostart(program=program, autostart=autostart)


if __name__ == '__main__':
    main()
