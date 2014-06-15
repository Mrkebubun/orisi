# Main Oracle file
from oracle_communication import OracleCommunication
from oracle_db import OracleDb, TaskQueue, UsedInput, SignedTransaction, HandledTransaction
from oracle_protocol import RESPONSE, SUBJECT
from condition_evaluator.evaluator import Evaluator

from settings_local import ORACLE_ADDRESS

from shared.bitcoind_client.bitcoinclient import BitcoinClient
from shared.bitmessage_communication.bitmessageclient import BitmessageClient

import time
import logging
import json
import re
from xmlrpclib import ProtocolError

# 3 minutes between oracles should be sufficient
HEURISTIC_ADD_TIME = 60 * 3

class Oracle:
  def __init__(self):
    self.communication = OracleCommunication()
    self.db = OracleDb()
    self.btc = BitcoinClient()
    self.evaluator = Evaluator()

    self.task_queue = TaskQueue(self.db)

    self.operations = {
      'TransactionRequest': self.add_transaction,
    }

  def condition_valid(self, condition):
    return self.evaluator.valid(condition) 

  def transaction_valid(self, transaction):
    return self.btc.is_valid_transaction(transaction)

  def add_transaction(self, message):
    body = json.loads(message.message)

    condition = body['condition']
    # Future reference - add parsing condition. Now assumed true
    if not self.condition_valid(condition):
      logging.debug("condition invalid")
      return

    transaction = body['raw_transaction']
    prevtx = body['prevtx']
    pubkey_list = body['pubkey_json']

    try:
      req_sigs = int(body['req_sigs'])
    except ValueError:
      logging.debug("req_sigs must be a number")
      return

    try:
      self.btc.add_multisig_address(req_sigs, pubkey_list)
    except ProtocolError:
      logging.debug("cant add multisig address")
      return

    if not self.transaction_valid(transaction):
      logging.debug("transaction invalid")
      return

    if not self.includes_me(prevtx):
      logging.debug("transaction does not include me")
      return

    if not self.btc.transaction_need_signature(transaction):
      logging.debug("transaction does not need a signature")
      return

    if not self.btc.transaction_contains_org_fee(transaction):
      logging.debug("org fee not found")
      return

    if not self.btc.transaction_contains_oracle_fee(transaction):
      logging.debug("oracle fee not found")
      self.communication.broadcast(SUBJECT.NO_FEE, RESPONSE.NO_FEE)
      return

    if self.btc.transaction_already_signed(transaction, prevtx):
      logging.debug("transaction already signed")
      return

    inputs, output = self.btc.get_inputs_outputs(transaction)

    used_input_db = UsedInput(self.db)
    for i in inputs:
      used_input = used_input_db.get_input(i)
      if used_input:
        if used_input["json_out"] != output:
          self.broadcast(
              SUBJECT.ADDRESS_DUPLICATE,
              RESPONSE.ADDRESS_DUPLICATE)
          return
    for i in inputs:
      used_input_db.save({
          'input_hash': i,
          'json_out': output
      })

    locktime = int(body['locktime'])
    turns = [self.get_my_turn(tx['redeemScript']) for tx in prevtx if 'redeemScript' in tx]
    my_turn = max(turns)
    add_time = my_turn * HEURISTIC_ADD_TIME

    task_queue = TaskQueue(self.db).save({
        "json_data": message.message,
        "filter_field": 'txid:{}'.format(self.btc.get_txid(transaction)),
        "done": 0,
        "next_check": locktime + add_time
    })

  def handle_request(self, request):
    operation, message = request
    fun = self.operations[operation]
    fun(message)

    # Save object to database for future reference
    db_class = self.db.operations[operation]
    if db_class:
      db_class(self.db).save(message)

  def get_my_turn(self, redeem_script):
    """
    Returns which one my address is in sorted (lexicographically) list of all
    addresses included in redeem_script.
    """
    addresses = sorted(self.btc.addresses_for_redeem(redeem_script))
    for idx, addr in enumerate(addresses):
      if self.btc.address_is_mine(addr):
        return idx
    return -1

  def includes_me(self, prevtx):
    for tx in prevtx:
      if not 'redeemScript' in tx:
        continue
      my_turn = self.get_my_turn(tx['redeemScript'])
      if my_turn >= 0:
        return True
    return False

  def check_condition(self, condition):
    return self.evaluator.evaluate(condition)

  def handle_task(self, task):
    body = json.loads(task["json_data"])
    condition = body["condition"]
    transaction = body["raw_transaction"]
    prevtx = body["prevtx"]
    if not self.check_condition(condition):
      self.task_queue.done(task)
      return
    if not self.transaction_valid(transaction):
      self.task_queue.done(task)
      return
    signed_transaction = self.btc.sign_transaction(transaction, prevtx)
    body["raw_transaction"] = signed_transaction
    SignedTransaction(self.db).save({"hex_transaction": signed_transaction, "prevtx":json.dumps(prevtx)})

    self.communication.broadcast_signed_transaction(json.dumps(body))
    self.task_queue.done(task)

  def filter_tasks(self, task):
    txid = task['filter_field']
    match = re.match(r'^txid:(.*)', txid)
    if not match:
      return
    txid = match.group(1)
    
    other_tasks = self.task_queue.get_similar(task)
    most_signatures = 0
    task_sig = []
    for task in other_tasks:
      body = json.loads(task['json_data'])
      raw_transaction = body['raw_transaction']
      prevtx = body['prevtx']
      signatures_for_tx = self.btc.signatures_needed(
          raw_transaction, 
          prevtx)
      task_sig.append((task, signatures_for_tx))
      most_signatures = max(most_signatures, signatures_for_tx)

    # If there is already a transaction that has MORE signatures than what we
    # have here - then ignore all tasks
    signs_for_transaction = HandledTransaction(self.db).signs_for_transaction(txid)

    if most_signatures == 0 or signs_for_transaction > most_signatures:
      redundant = [t[0] for t in task_sig]
    else:
      tasks_to_do = [t[0] for t in task_sig if t[1] == most_signatures]
      redundant = [t[0] for t in task_sig if t not in tasks_to_do]

    HandledTransaction(self.db).update_tx(txid, most_signatures)
    for r in redundant:
      self.task_queue.done(r)
    return tasks_to_do

  def task_round(self):
    task = self.task_queue.get_oldest_task()
    tasks = self.filter_tasks(task)
    for task in tasks:
      self.handle_task(task)

  def run(self):
    
    if not ORACLE_ADDRESS:
      new_addr = self.btc.server.getnewaddress()
      logging.error("first run? add '%s' to ORACLE_ADDRESS in settings_local.py" % new_addr)
      exit()

    logging.info("my multisig address is %s" % ORACLE_ADDRESS)

    while True:
      # Proceed all requests
      requests = self.communication.get_new_requests()
      logging.debug("{0} new requests".format(len(requests)))
      for request in requests:
        self.handle_request(request)
        self.communication.mark_request_done(request)

      self.task_round()

      time.sleep(1)
