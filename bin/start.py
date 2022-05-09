#!/usr/bin/env python3

import sys
import argparse


__base_worker__ = 'BaseWorker'


WORKERS_CLASSES = {
    'stats_fetcher': 'StatsFetcher',
    'flows_applier': 'FlowsApplier',
    'flows_sync': 'FlowsSync',
    'device_controller': 'DeviceController'
}


def main():
    parser = argparse.ArgumentParser(description='Secunity\'s Process Start')

    parser.add_argument('--program', type=str, help='program to start')
    args = parser.parse_args()

    program = args.program
    if not program or program not in ('stats_fetcher', 'flows_applier', 'flows_sync', 'device_controller'):
        raise ValueError(f'invalid program: "{program}"')

    from pathlib import Path

    path = Path(__file__)
    parent_path = str(path.parent.absolute())
    expected_path = str(path.parent.parent.absolute())
    if expected_path not in sys.path:
        sys.path.insert(0, expected_path)
    if parent_path in sys.path:
        sys.path.remove(parent_path)

    expected_class = WORKERS_CLASSES[program]

    import importlib
    mdl = importlib.import_module(f'workers.{program}')

    worker_cls = next((getattr(mdl, _) for _ in dir(mdl) if str(_) == expected_class), None)
    if not worker_cls:
        raise ValueError(f'could not resolve starting point, program: "{program}"')

    worker = worker_cls()
    worker.start()


if __name__ == '__main__':
    main()
