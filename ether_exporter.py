#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
from web3 import Web3, HTTPProvider
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "WARNING"))

settings = {}

def _settings():
    global settings

    settings = {
        'ether_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'ether_uri': 'http://localhost:8545',
            'additional_accounts': [],
            'enable_accounts': 'on',
            'export': 'text',
            'listen_port': 9305,
            'listen_address': '127.0.0.1'
        },
    }
    config_file = '/etc/ether_exporter.yml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('ether_exporter'):
        if cfg['ether_exporter'].get('prom_folder'):
            settings['ether_exporter']['prom_folder'] = cfg['ether_exporter']['prom_folder']
        if cfg['ether_exporter'].get('interval'):
            settings['ether_exporter']['interval'] = cfg['ether_exporter']['interval']
        if cfg['ether_exporter'].get('ether_uri'):
            settings['ether_exporter']['ether_uri'] = cfg['ether_exporter']['ether_uri']
        if cfg['ether_exporter'].get('additional_accounts'):
            settings['ether_exporter']['additional_accounts'] = cfg['ether_exporter']['additional_accounts']
        if cfg['ether_exporter'].get('export') in ['text', 'http']:
            settings['ether_exporter']['export'] = cfg['ether_exporter']['export']
        if cfg['ether_exporter'].get('enable_accounts') in ['on', 'off']:
            settings['ether_exporter']['enable_accounts'] = cfg['ether_exporter']['enable_accounts']
        if cfg['ether_exporter'].get('listen_port'):
            settings['ether_exporter']['listen_port'] = cfg['ether_exporter']['listen_port']
        if cfg['ether_exporter'].get('listen_address'):
            settings['ether_exporter']['listen_address'] = cfg['ether_exporter']['listen_address']

class EthereumCollector:
    def collect(self):
        metrics = {
            'ether_current_block': GaugeMetricFamily('ether_block_number', 'The number of the most recent block'),
            'ether_gas_price_wei': GaugeMetricFamily('ether_gas_price_wei', 'The current gas price in Wei'),
            'ether_mining': GaugeMetricFamily('ether_mining', 'Boolean mining status'),
            'ether_hash_rate': GaugeMetricFamily(
                'ether_hash_rate',
                'The current number of hashes per second the node is mining with'
            ),
            'ether_syncing': GaugeMetricFamily('ether_syncing', 'Boolean syncing status'),
            'ether_lag': GaugeMetricFamily('ether_lag', 'The difference between highestBlock and currentBlock'),
            'ether_peers': GaugeMetricFamily('ether_peers', 'The number of ethereum peers'),
        }
        if settings['ether_exporter']['enable_accounts'] == 'on':
            metrics.update({
                'account_balance': GaugeMetricFamily(
                    'account_balance',
                    'Account Balance',
                    labels=['currency', 'account', 'type']
                ),
            })
        web3 = Web3(HTTPProvider(settings['ether_exporter']['ether_uri']))
        if web3:
            if settings['ether_exporter']['enable_accounts'] == 'on':
                accounts = set(web3.eth.accounts)
                for additional_account in settings['ether_exporter']['additional_accounts']:
                    accounts.add(additional_account)
                log.debug('Exporting metrics for the following accounts: {acc}'.format(acc=accounts))
                for account in accounts:
                    # metric: ether_account_balance
                    try:
                        metrics['account_balance'].add_metric(
                            labels=['ETH', account, 'ether'],
                            value=web3.fromWei(web3.eth.getBalance(account), 'ether')
                        )
                    except (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ReadTimeout
                    ) as e:
                        log.warning("Can't connect to Ethereum node. The error received follows.")
                        log.warning(e)
            # metric: ether_current_block
            try:
                metrics['ether_current_block'].add_metric(value=web3.eth.blockNumber, labels=[])
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout
            ) as e:
                log.warning("Can't connect to Ethereum node. The error received follows.")
                log.warning(e)
            except ValueError as e:
                log.warning("Can't get the value for ether_current_block. The error received follows.")
                log.warning(e)

            # metric: ether_gas_price_wei
            try:
                metrics['ether_gas_price_wei'].add_metric(value=web3.eth.gasPrice, labels=[])
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout
            ) as e:
                log.warning("Can't connect to Ethereum node. The error received follows.")
                log.warning(e)
            except ValueError as e:
                log.warning("Can't get the value for ether_gas_price_wei. The error received follows.")
                log.warning(e)

            # metric: ether_mining
            # metric: ether_hash_rate
            try:
                if web3.eth.mining:
                    metrics['ether_mining'].add_metric(value=1, labels=[])
                    metrics['ether_hash_rate'].add_metric(value=web3.eth.hashrate, labels=[])
                else:
                    metrics['ether_mining'].add_metric(value=0, labels=[])
                    metrics['ether_hash_rate'].add_metric(value=0, labels=[])
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout
            ) as e:
                log.warning("Can't connect to Ethereum node. The error received follows.")
                log.warning(e)
            except ValueError as e:
                log.warning("Can't get the value for ether_mining or ether_hash_rate. The error received follows.")
                log.warning(e)
            # metric: ether_syncing
            # metric: ether_lag
            try:
                if web3.eth.syncing:
                    ether_lag = int(web3.eth.syncing['highestBlock']-web3.eth.syncing['currentBlock'])
                    metrics['ether_syncing'].add_metric(value=1, labels=[])
                    metrics['ether_lag'].add_metric(value=ether_lag, labels=[])

                else:
                    metrics['ether_syncing'].add_metric(value=0, labels=[])
                    metrics['ether_lag'].add_metric(value=0, labels=[])
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout
            ) as e:
                log.warning("Can't connect to Ethereum node. The error received follows.")
                log.warning(e)
            except ValueError as e:
                log.warning("Can't get the value for ether_syncing. The error received follows.")
                log.warning(e)
            # metric: peer_count
            try:
                if web3.net.peerCount:
                    metrics['ether_peers'].add_metric(value=web3.net.peerCount, labels=[])
                else:
                    metrics['ether_peers'].add_metric(value=0, labels=[])
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout
            ) as e:
                log.warning("Can't connect to Ethereum node. The error received follows.")
                log.warning(e)
            except ValueError as e:
                log.warning("Can't get the value for ether_peers. The error received follows.")
                log.warning(e)

        web3 = None

        for m in metrics.values():
            yield m

def _collect_to_text():
    while True:
        e = EthereumCollector()
        write_to_textfile('{0}/ether-exporter.prom'.format(settings['ether_exporter']['prom_folder']), e)
        time.sleep(int(settings['ether_exporter']['interval']))


def _collect_to_http():
    start_http_server(int(settings['ether_exporter']['listen_port']), addr=settings['ether_exporter']['listen_address'])
    while True:
        time.sleep(int(1))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    REGISTRY.register(EthereumCollector())
    if settings['ether_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['ether_exporter']['export'] == 'http':
        _collect_to_http()

