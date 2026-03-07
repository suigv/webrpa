from core.account_parser import parse_accounts_advanced
import json

sample_data = """DominicBru61726----z5t5v77GG7----ChristineGuzman3012@hotmail.com----dcrqrcgq443013----a93e84c46c20622929de91bc255613d89b59ccee----CKIJF5DRMYA4VRPZ"""
mapping = { "0": "account", "1": "password", "2": "email", "3": "email_password", "4": "token", "5": "twofa" }
delimiter = "----"

result = parse_accounts_advanced(sample_data, delimiter=delimiter, mapping=mapping)
print(f"Valid count: {result['valid']}")
print(f"Accounts: {result['accounts']}")
if result['errors']:
    print(f"Errors: {result['errors']}")
