import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from settings_local import *

import decimal
import json
import jsonrpclib
from xmlrpclib import ProtocolError


class BitcoinClient:

  def __init__(self):
    self.connect()

  def connect(self):
    self.server = jsonrpclib.Server('http://{0}:{1}@{2}:{3}'.format(
        BITCOIND_RPC_USERNAME,
        BITCOIND_RPC_PASSWORD,
        BITCOIND_RPC_HOST,
        BITCOIND_RPC_PORT))

  def keep_alive(fun):
    def ping_and_reconnect(self, *args, **kwargs):
      try:
        # Cheap API call that checks wether we're connected
        self.server.help()
      except:
        self.connect()
      return fun(self, *args, **kwargs)
    return ping_and_reconnect

  @keep_alive
  def _get_json_transaction(self, hex_transaction):
    return self.server.decoderawtransaction(hex_transaction)

  @keep_alive
  def sign_transaction(self, raw_transaction):
    result = self.server.signrawtransaction(transaction)
    return result['hex']

  @keep_alive
  def is_valid_transaction(self, raw_transaction):
    # Is raw transaction valid and decodable?
    try:
      transaction = self._get_json_transaction(raw_transaction)
    except ProtocolError:
      return False
    return True

  @keep_alive
  def get_inputs_outputs(self, raw_transaction):
    transaction = self._get_json_transaction(raw_transaction)
    transaction_dict = json.loads(transaction)
    vin = transaction_dict["vin"]
    vouts = transaction_dict["vout"]
    result = (
        sorted([json.dumps({'txid': tx_input['txid'], 'vout':tx_input['vout']}) for tx_input in vin]),
        json.dumps(
            {
              'vout': sorted([
                {
                  "value": vout["value"], 
                  "addresses": vout["scriptPubKey"]["addresses"]
                } for vout in vouts
              ])
            }
        )
    )

    return result

  @keep_alive
  def transaction_already_signed(self, raw_transaction):
    signed_transaction = self.sign_transaction(raw_transaction)
    if signed_transaction['hex'] == raw_transaction:
      return True
    return False

  @keep_alive
  def transaction_contains_oracle_fee(self, raw_transaction):
    transaction = self._get_json_transaction(raw_transaction)
    transaction_dict = json.dumps(transaction)
    if not 'vout' in transaction_dict:
      return False
    for vout in transaction_dict['vout']:
      # Sanity checks
      if not 'value' in vout:
        continue
      if not 'scriptPubKey' in vout:
        continue
      if not 'addresses' in vout['scriptPubKey']:
        continue

      for address in vout['scriptPubKey']['addresses']:
        if address == ORACLE_ADDRESS:
          value = Decimal(vout['value'])
          if value >= Decimal(ORACLE_FEE):
            return True
    return False


