
import json
import time
from nacl.signing import SigningKey
from common import query_order, cancel_order, taker_clean_position, get_price, create_order, maker_clean_position


POSITION = 500


def main():
    with open("standx_beggar_auth.json", "r") as f:
        auth_json = json.load(f)
        auth = {
            'access_token': auth_json['access_token'],
            'signing_key': SigningKey(bytes.fromhex(auth_json['signing_key'])),
        }
    print("Starting beggar bot...")



if __name__ == "__main__":
    main()
