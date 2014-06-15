from oracle import Oracle
from oracle_db import OracleDb, TaskQueue, TransactionRequestDb

from shared.bitmessage_communication.bitmessagemessage import BitmessageMessage

import base64
import os
import unittest

from collections import defaultdict

TEMP_DB_FILE = 'temp_db_file.db'

def create_message():
  msg_dict = defaultdict(lambda: 'dummy')
  msg_dict['receivedTime'] = 1000
  msg_dict['subject'] = base64.encodestring('dummy')
  msg_dict['message'] = base64.encodestring("""
    {"raw_transaction": "010000000144c1ae801383d9e65df8b0f7c6d65f976ceb3c087d3b33c7087f66388f581cfb00000000fd4101004730440220148ce15f921b2e073b70b4b1aa32f3e13bed7992d94ff1d48cba15323ceb1ac1022047bf4c17628a37baa2107cb0b117272c8ecfd57c94fd73248c3ca1a824b470dd01483045022100c6da3c358d50f05cd7e72f92b46449486fef9f3a8a8ff75047c60a566227823c02205187c4edb265ed9672ede1f52d1dab9925cf6af2ba930f2319fbbc0d454697bb014cad542102e6cc83f0e811464e02a0b003d172ddc7ca5342f587306b7f9ff26d4170e5c02a21022864b2e3d86a38dc7f75b681f8461763a7777cd250708a4fb7b5af69255f444c2103a3f790ee5f9c7a2383c62fbc96a8490fffe2c5ea3bff7a8ee050ed4e272ce9962103c46985b570636543289971f1ea787119bd79d0041cc4be284e4a591c7dd9bbc5210271e5a37045b3a41474286deeba84667ac962548bddafc7f8359e2a80995b5da555aeffffffff01204e0000000000001976a914f77ddab3ea50377e1ce8995b1eb52310e43b43e988ac00000000", 
    "prevtx": [{"txid": "fb1c588f38667f08c7333b7d083ceb6c975fd6c6f7b0f85de6d9831380aec144","vout": 0, "redeemScript":"542102e6cc83f0e811464e02a0b003d172ddc7ca5342f587306b7f9ff26d4170e5c02a21022864b2e3d86a38dc7f75b681f8461763a7777cd250708a4fb7b5af69255f444c2103a3f790ee5f9c7a2383c62fbc96a8490fffe2c5ea3bff7a8ee050ed4e272ce9962103c46985b570636543289971f1ea787119bd79d0041cc4be284e4a591c7dd9bbc5210271e5a37045b3a41474286deeba84667ac962548bddafc7f8359e2a80995b5da555ae","scriptPubKey":"a9141cd14546dd7cfeee3b5bdf56d46423acefa51d7687"}], 
    "pubkey_json": ["02e6cc83f0e811464e02a0b003d172ddc7ca5342f587306b7f9ff26d4170e5c02a","022864b2e3d86a38dc7f75b681f8461763a7777cd250708a4fb7b5af69255f444c","03a3f790ee5f9c7a2383c62fbc96a8490fffe2c5ea3bff7a8ee050ed4e272ce996","03c46985b570636543289971f1ea787119bd79d0041cc4be284e4a591c7dd9bbc5","0271e5a37045b3a41474286deeba84667ac962548bddafc7f8359e2a80995b5da5"], 
    "req_sigs": 4, 
    "operation": "transaction", 
    "locktime": 1402318623, 
    "condition": "True"}
    """)
  message = BitmessageMessage(
      msg_dict,
      'dummyaddress')
  return message
  

class MockOracleDb(OracleDb):
  def __init__(self):
    self._filename = TEMP_DB_FILE
    self.connect()
    operations = {
      'TransactionRequest': TransactionRequestDb
    }
    self.operations = defaultdict(lambda: False, operations)

class OracleTests(unittest.TestCase):
  def setUp(self):
    self.oracle = Oracle()
    self.db = MockOracleDb()
    self.oracle.db = self.db
    self.oracle.task_queue = TaskQueue(self.db)

  def tearDown(self):
    os.remove(TEMP_DB_FILE)

  def test_add_transaction(self):
    message = create_message()
    request = ('TransactionRequest', message)
    self.oracle.handle_request(request)
    self.assertEqual(len(TaskQueue(self.db).get_all_tasks()), 1)

  def test_add_task(self):
    message = create_message()
    request = ('TransactionRequest', message)
    self.oracle.handle_request(request)
    task = self.oracle.task_queue.get_oldest_task()
    tasks = self.oracle.filter_tasks(task)
    self.assertEqual(len(tasks), 1)

    self.oracle.task_queue.done(tasks[0])

    task = self.oracle.task_queue.get_oldest_task()
    self.assertIsNone(task)


  