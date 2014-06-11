import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import time
import hashlib
import json
import logging

from shared.bitcoind_client.bitcoinclient import BitcoinClient
from shared.bitmessage_communication.bitmessageclient import BitmessageClient
from shared import liburl_wrapper
from client_db import (
    ClientDb, 
    SignatureRequestDb, 
    MultisigRedeemDb,
    RawTransactionDb,
    OracleListDb,
    OracleCheckDb)

URL_ORACLE_LIST = 'http://oracles.li/list-default.json'
MINIMUM_DIFFERENCE = 1 # in seconds

class OracleClient:
  def __init__(self):
    self.btc = BitcoinClient()
    self.bm = BitmessageClient()
    self.db = ClientDb()
    self.update_oracle_list()

  def update_oracle_list(self):
    last_check = OracleCheckDb(self.db).get_last()
    current_time = int(time.time())
    if last_check:
      last_time = int(last_check['last_check'])
    else:
      last_time = 0
    if current_time - last_time  > MINIMUM_DIFFERENCE:
      content = liburl_wrapper.safe_read(URL_ORACLE_LIST, timeout_time=10)
      try:
        oracle_list = json.loads(content)
        oracle_list = oracle_list['nodes']
        for oracle in oracle_list:
          self.add_oracle(oracle['public_key'], oracle['address'], oracle['fee'])
      except ValueError:
        logging.error("oracle list json invalid")
      OracleCheckDb(self.db).save({"last_check": current_time})


  def create_multisig_address(self, client_pubkey, oracle_pubkey_list_json, min_sigs):
    oracle_pubkey_list = json.loads(oracle_pubkey_list_json)
    max_sigs = len(oracle_pubkey_list)
    difference = max_sigs - min_sigs

    real_min_sigs = max_sigs + 1
    client_sig_number = difference + 1

    key_list = [client_pubkey for _ in range(client_sig_number)] + oracle_pubkey_list
    response = self.btc.create_multisig_address(real_min_sigs, key_list)

    MultisigRedeemDb(self.db).save({
        "multisig": response['address'], 
        "min_sig": real_min_sigs,
        "redeem_script": response['redeemScript'],
        "pubkey_json": json.dumps(sorted(key_list))})

    self.btc.server.addmultisigaddress(real_min_sigs, key_list)
    return response

  def create_multisig_transaction(self, input_txids, outputs):
    transaction_hex = self.btc.create_transaction(input_txids, outputs)
    return transaction_hex

  def sign_transaction(self, hex_transaction):
    signed_hex_transaction = self.btc.sign_transaction(hex_transaction)
    return signed_hex_transaction

  def prepare_request(self, transaction, locktime, condition, prevtx):
    message = json.dumps({
      "operation": "transaction",
      "raw_transaction": signed_transaction,
      "locktime": locktime,
      "condition": condition,
      "prevtx": prevtx
    })
    return message

  def save_transaction(self, request):
    try:
      raw_request = json.loads(request)
    except ValueError:
      logging.error("request is invalid JSON")
      return
    prevtx = json.dumps(raw_request['prevtx'])
    prevtx_hash = hashlib.sha256(prevtx).hexdigest()
    SignatureRequestDb(self.db).save({"prevtx_hash": prevtx_hash, "json_data": request})

  def send_transaction(self, request):
    self.save_transaction(request)
    self.bm.send_message(self.bm.chan_address, "TransactionRequest", request)

  def add_raw_transaction(self, raw_transaction):
    if not self.btc.is_valid_transaction(raw_transaction):
      logging.error("hex transaction is not valid transaction")
    transaction_json = self.btc._get_json_transaction(raw_transaction)
    txid = transaction_json['txid']
    RawTransactionDb(self.db).save({
        "txid": txid,
        "raw_transaction": raw_transaction})
    return txid

  def add_oracle(self, pubkey, address, fee):
    OracleListDb(self.db).save({
        "pubkey": pubkey,
        "address": address,
        "fee": fee})