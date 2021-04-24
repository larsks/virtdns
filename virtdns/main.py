import asyncio
import click
import json
import logging
import watchgod

from pathlib import Path

LOG = logging.getLogger(__name__)


class VDNS:
    def __init__(self, macs_file, status_file, hosts_file,
                 domains=None):
        self.macs_file = Path(macs_file)
        self.status_file = Path(status_file)
        self.hosts_file = Path(hosts_file)
        self.hosts = {}
        self.domains = domains if domains else []

    def run(self):
        asyncio.run(self.loop())

    async def loop(self):
        self.q = asyncio.Queue()

        tasks = [  # NOQA
            asyncio.create_task(self.watch_file(self.macs_file)),
            asyncio.create_task(self.watch_file(self.status_file)),
        ]

        self.read_libvirt_data()
        self.write_hosts_file()

        while True:
            event = await self.q.get()
            LOG.debug('received event: %s', event)

            self.read_libvirt_data()
            self.write_hosts_file()

    def read_libvirt_data(self):
        hosts = {}

        with self.macs_file.open('r') as fd:
            try:
                data = json.load(fd)

                for entry in data:
                    if any(entry['domain'].endswith(f'.{domain}') for domain in self.domains):
                        LOG.info('found hostname %s', entry['domain'])
                        for mac in entry['macs']:
                            LOG.debug('adding host %s at %s', entry['domain'], mac)
                            hosts[mac] = {
                                'name': entry['domain'],
                            }
                    else:
                        LOG.debug('ignore hostname %s (unknown domain)', entry['domain'])
            except json.JSONDecodeError:
                LOG.warning('failed to read macs file')

        with self.status_file.open('r') as fd:
            try:
                data = json.load(fd)

                for entry in data:
                    if entry['mac-address'] in hosts:
                        hosts[entry['mac-address']]['address'] = entry['ip-address']
                    else:
                        LOG.debug('ignore MAC %s (no matching host)', entry['mac-address'])
            except json.JSONDecodeError:
                LOG.warning('failed to read status file')

        self.hosts = hosts

    async def watch_file(self, path):
        LOG.debug('starting watcher for %s', path)
        async for events in watchgod.awatch(path):
            for event in events:
                await self.q.put(event)

    def write_hosts_file(self):
        with self.hosts_file.open('w') as fd:
            for entry in self.hosts.values():
                if 'name' in entry and 'address' in entry:
                    fd.write('{address} {name}\n'.format(**entry))


@click.command()
@click.option('-d', '--domain', 'domains', multiple=True)
@click.option('-h', '--hosts-file', default='dnsmasq.hosts')
@click.option('-b', '--bridge', default='virbr0')
@click.option('-M', '--mac-file')
@click.option('-S', '--status-file')
@click.option('-v', '--verbose', count=True)
def main(domains, hosts_file, bridge, mac_file, status_file, verbose):
    try:
        loglevel = ['WARNING', 'INFO', 'DEBUG'][verbose]
    except IndexError:
        loglevel = 'DEBUG'

    logging.basicConfig(level=loglevel)

    if mac_file is None:
        mac_file = Path(f'/var/lib/libvirt/dnsmasq/{bridge}.macs')
    if status_file is None:
        status_file = Path(f'/var/lib/libvirt/dnsmasq/{bridge}.status')

    app = VDNS(mac_file, status_file, hosts_file, domains=domains)
    app.run()
