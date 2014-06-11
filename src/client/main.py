from collections import defaultdict
from client import OracleClient
import sys
import json

# Fixed for now, TODO: get better estimation of how big fee should be
MINERS_FEE = 0.0001

def unknown(args):
  print "unknown operation, use ./main.py help for possible operations"

def get_multi_address(args):
  """
  Takes your public key, list of oracles' public keys as json and number of signatures
  needed for signing. Returns multisig_address and redeemScript as JSON
  """
  if len(args) < 3:
    print "Not enough arguments"
    return
  c = OracleClient()
  client_pubkey = args[0]
  oracle_pubkeys = args[1]
  try:
    number_of_sigs = int(args[2])
  except ValueError:
    print "number_of_sigs must be int"
  print c.create_multisig_address(client_pubkey, oracle_pubkeys, number_of_sigs)
  print "send bitcoins you want to use to that transaction, then add transaction \
      either with addrawtransaction (hex transaction as argument), or with \
      addtransaction (txid as argument, ONLY IF the transaction was send locally, \
      from your current bitcoind)"

def describe_protocol(args):
  """Describes how to create full transaction step by step"""
  steps = [
    "Get oracles' public addresses as json list",
    "Create transaction with getmultiaddress (python main.py help for more info)",
    "Send coins you want to lock on that address, save transaction",
    "Use addrawtransaction to save transaction you've created (see more with help)"
  ]
  for idx, step in enumerate(steps):
    print "{}. {}".format(idx+1, step)

def create_transaction(args):
  """
  Creates raw transaction
  Arguments:
  1. Input txids, vout - json of list of elements:
  [{
    "txid": "a93..."
    "vout: 0
  }, ...]
  2. Outputs, json:
  {
    "address1": amount1,
    "address2": amount2,
    ...
  }
  """
  if len(args) < 2:
    print "Not enough arguments"
    return
  c = OracleClient()
  return c.create_multisig_transaction(args[0], args[1])

def create_signed_transaction(args):
  """
  Creates raw transaction and signs it.
  Arguments:
  1. Input txids, vout - json of list of elements:
  [{
    "txid": "a93..."
    "vout: 0
  }, ...]
  2. Outputs, json:
  {
    "address1": amount1,
    "address2": amount2,
    ...
  }
  """
  raw_transaction =  create_transaction(args)
  signed_transaction = OracleClient().sign_transaction(raw_transaction)
  return signed_transaction

def prepare_transaction_request(args):
  try:
    locktime = int(args[0])
  except ValueError:
    print "locktime must be int"
    return
  signed_transaction = args[1]
  prevtx = args[2]
  try:
    condition = args[3]
  except IndexError:
    # For now we do not verify conditions
    condition = "True"
  return OracleClient().prepare_request(signed_transaction, locktime, condition, prevtx)

def send_transaction(args):
  """
  Sends transaction to bitmessage network
  Takes locktime, signed_raw_transaction, condition (optional)
  """
  transaction = prepare_transaction_request(args)
  if not transaction:
    return
  OracleClient().send_transaction(transaction)

def add_raw_transaction(args):
  """
  Adds hex transaction to DB, it will be used later 
  to create your multisig transaction.
  """
  if len(args) < 1:
    print "not enough arguments"
    return
  raw_transaction = args[0]
  txid = OracleClient().add_raw_transaction(raw_transaction)
  print txid

def add_transaction_by_txid(args):
  """
  TODO
  """
  pass

def add_oracle(args):
  """
  Adds Oracle to Oracle Database. Takes three arguments
  (pubkey, address, fee).
  """
  if len(args) < 3:
    print "not enough arguments"
    return
  pubkey = args[0]
  address = args[1]
  fee = args[2]
  OracleClient().add_oracle(pubkey, address, fee)

RAW_OPERATIONS = {
  'getmultiaddress': get_multi_address,
  'describeprotocol': describe_protocol,
  'createtransaction': create_transaction,
  'createsignedtransaction': create_signed_transaction,
  'preparetransaction': prepare_transaction_request,
  'addrawtransaction': add_raw_transaction,
  'addtransaction': add_transaction_by_txid,
  'addoracle': add_oracle,
}
OPERATIONS = defaultdict(lambda:unknown, RAW_OPERATIONS)



def help():
  print "You can use one of the following functions:"
  for name, fun in RAW_OPERATIONS.iteritems():
    print "{0} - {1}".format(name, fun.__doc__) 

def main(args):
  if len(args) == 0:
    print "no arguments given, use ./main.py help for possible operations"
    return
  if args[0] == 'help':
    help()
    return
  operation = OPERATIONS[args[0]]
  #special case
  operation(args[1:])


if __name__=="__main__":
  args = sys.argv[1:]
  main(args)